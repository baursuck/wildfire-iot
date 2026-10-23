"""Server side: subscribes to all towers, stores events, locates the fire and alerts the operator in Telegram."""
import base64
import json
import math
import os
import threading
import time

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv

import config

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG = f"https://api.telegram.org/bot{TOKEN}"

FUSION_WINDOW_S = 15 * 60   # detections from different towers this close in time are treated as one fire
EVENTS_DIR = "out/events"

latest_weather = {}
recent = {}   # tower_id -> last detection payload


def to_local_km(lat, lon, lat0, lon0):
    return (lon - lon0) * 111.32 * math.cos(math.radians(lat0)), (lat - lat0) * 110.57


def from_local_km(x, y, lat0, lon0):
    return lat0 + y / 110.57, lon0 + x / (111.32 * math.cos(math.radians(lat0)))


def triangulate(t1, az1, t2, az2):
    """Intersect two bearing rays from towers t1 and t2. Returns (lat, lon, d1_km, d2_km, crossing_angle) or None."""
    x2, y2 = to_local_km(t2["lat"], t2["lon"], t1["lat"], t1["lon"])
    d1 = (math.sin(math.radians(az1)), math.cos(math.radians(az1)))
    d2 = (math.sin(math.radians(az2)), math.cos(math.radians(az2)))
    det = d1[0] * -d2[1] - d1[1] * -d2[0]
    if abs(det) < 1e-6:
        return None
    # Solve t1*d1 - t2*d2 = p2 for the two ray lengths.
    a = (x2 * -d2[1] - y2 * -d2[0]) / det
    b = (d1[0] * y2 - d1[1] * x2) / det
    angle = abs((az1 - az2 + 180) % 360 - 180)
    if a <= 0 or b <= 0 or angle < 15:
        return None
    lat, lon = from_local_km(a * d1[0], a * d1[1], t1["lat"], t1["lon"])
    return lat, lon, a, b, angle


def telegram(method, **kwargs):
    if not TOKEN or not CHAT_ID:
        print(f"[telegram] skipped {method}: TELEGRAM_CHAT_ID not set")
        return
    try:
        r = requests.post(f"{TG}/{method}", timeout=20, **kwargs)
        if not r.ok:
            print(f"[telegram] {method} failed: {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[telegram] {method} error: {e}")


def weather_line(tower_id):
    w = latest_weather.get(tower_id)
    if not w:
        return ""
    return f"\n🌡 {w['t']}°C   💧 {w['rh']}%   💨 {w['ws']} m/s from {w['wd']}°"


def on_detection(client, d):
    tid = d["tower_id"]
    tower = config.TOWERS[tid]
    os.makedirs(EVENTS_DIR, exist_ok=True)
    jpeg = base64.b64decode(d["snapshot_jpeg_b64"])
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(d["ts"]))
    with open(f"{EVENTS_DIR}/{stamp}_{tid}.jpg", "wb") as f:
        f.write(jpeg)
    record = {k: v for k, v in d.items() if k != "snapshot_jpeg_b64"}
    with open(f"{EVENTS_DIR}/events.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[backend] detection {tid} conf={d['confidence']} az={d['azimuth_deg']}")

    caption = (f"🔥 <b>Smoke detected</b> — {tid.upper()} {tower['name']}\n"
               f"Confidence <b>{d['confidence']:.2f}</b>, confirmed on {d['frames_confirmed']} frames in a row\n"
               f"Bearing <b>{d['azimuth_deg']:.1f}°</b>"
               f"{weather_line(tid)}\n"
               f"🕒 {time.strftime('%H:%M:%S', time.localtime(d['ts']))}")
    threading.Thread(target=telegram, args=("sendPhoto",), kwargs={
        "data": {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
        "files": {"photo": ("smoke.jpg", jpeg, "image/jpeg")}}).start()

    recent[tid] = d
    for other_id, o in recent.items():
        if other_id == tid or d["ts"] - o["ts"] > FUSION_WINDOW_S:
            continue
        fix = triangulate(config.TOWERS[other_id], o["azimuth_deg"], tower, d["azimuth_deg"])
        if not fix:
            continue
        lat, lon, d1, d2, angle = fix
        fire = {"lat": round(lat, 5), "lon": round(lon, 5), "towers": [other_id, tid],
                "distances_km": [round(d1, 2), round(d2, 2)], "crossing_angle_deg": round(angle, 1), "ts": time.time()}
        client.publish(f"{config.TOPIC_ROOT}/server/fire", json.dumps(fire), qos=1, retain=True)
        print(f"[backend] fire located at {lat:.5f}, {lon:.5f}")
        text = (f"📍 <b>Fire located by triangulation</b>\n"
                f"{lat:.5f}, {lon:.5f}\n"
                f"{d1:.1f} km from {other_id.upper()}, {d2:.1f} km from {tid.upper()}, rays cross at {angle:.0f}°\n"
                f"<a href=\"https://maps.google.com/?q={lat:.5f},{lon:.5f}\">Open in Google Maps</a>")
        threading.Thread(target=lambda: (
            telegram("sendLocation", data={"chat_id": CHAT_ID, "latitude": lat, "longitude": lon}),
            telegram("sendMessage", data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
                                          "disable_web_page_preview": True}))).start()


def on_sim_fire(d):
    """A fire placed on the interactive slide: same alert path, marked as a simulation."""
    lines = [f"{t['id']}  {t['bearing']:.1f}°  ·  {t['km']:.1f} km" for t in d.get("towers", [])]
    sensor = "thermal" if d.get("sensor") == "ir" else "optical"
    camera = "360° scan" if d.get("camera") == "360" else "fixed 64°"
    est = d.get("estimate")
    print(f"[backend] simulated fire from slide: {len(lines)} towers, estimate={est}")
    if est:
        head = (f"📍 <b>Fire located</b> (simulation)\n{est['lat']:.5f}, {est['lon']:.5f}  ·  error {est['error_m']} m\n"
                f"<a href=\"https://maps.google.com/?q={est['lat']:.5f},{est['lon']:.5f}\">Open in Google Maps</a>")
    else:
        head = "🔥 <b>Smoke direction only</b> (simulation)\nOne tower sees it: range needs a second tower or terrain."
    text = f"{head}\n\n" + "\n".join(lines) + f"\n\n{sensor} · {camera}"
    def send():
        if est:
            telegram("sendLocation", data={"chat_id": CHAT_ID, "latitude": est["lat"], "longitude": est["lon"]})
        telegram("sendMessage", data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
                                      "disable_web_page_preview": True})
    threading.Thread(target=send).start()


def on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    try:
        payload = json.loads(msg.payload)
    except ValueError:
        return
    if parts[-1] == "weather":
        latest_weather[parts[1]] = payload
    elif parts[-1] == "status" and parts[1] in config.TOWERS:
        print(f"[backend] {parts[1]} is {payload.get('state')}")
    elif parts[-1] == "detection":
        on_detection(client, payload)
    elif parts[1] == "sim" and parts[-1] == "fire":
        on_sim_fire(payload)


def main():
    if not CHAT_ID:
        print("TELEGRAM_CHAT_ID is empty: alerts will only be printed. Run `python telegram_setup.py`.")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="backend")
    client.on_message = on_message
    client.on_connect = lambda c, u, f, rc, p: c.subscribe([(f"{config.TOPIC_ROOT}/+/+", 1)])
    client.connect(config.MQTT_HOST, config.MQTT_PORT)
    # The previous run's fire marker is retained on the broker; clear it so the map starts clean.
    client.publish(f"{config.TOPIC_ROOT}/server/fire", b"", retain=True)
    print("[backend] listening on wildfire/+/+")
    client.loop_forever()


if __name__ == "__main__":
    main()
