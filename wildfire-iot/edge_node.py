"""Edge node of a camera tower: runs smoke detection next to the camera and publishes only events over MQTT.

Source can be a folder of FIgLib frames, a video file, a webcam index or an RTMP/RTSP stream (e.g. the drone).
"""
import argparse
import base64
import glob
import json
import math
import os
import re
import subprocess
import time

import cv2
import paho.mqtt.client as mqtt
from ultralytics import YOLO

import config

FIGLIB_OFFSET = re.compile(r"_([+-]\d+)\.jpg$")


def figlib_offset_min(path):
    m = FIGLIB_OFFSET.search(path)
    return int(m.group(1)) // 60 if m else None


def frame_source(source):
    """Yield (frame, ignition_offset_minutes_or_None)."""
    if os.path.isdir(source):
        files = sorted(glob.glob(os.path.join(source, "*.jpg")), key=lambda f: figlib_offset_min(f) or 0)
        for f in files:
            yield cv2.imread(f), figlib_offset_min(f)
        return
    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        yield frame, None
    cap.release()


def azimuth_deg(cx, width, tower):
    """Bearing to a pixel column with a pinhole camera model: heading + atan(dx / f)."""
    f = (width / 2) / math.tan(math.radians(tower["hfov_deg"] / 2))
    return (tower["heading_deg"] + math.degrees(math.atan((cx - width / 2) / f))) % 360


def jpeg_bytes(img, width, quality):
    h = int(img.shape[0] * width / img.shape[1])
    ok, buf = cv2.imencode(".jpg", cv2.resize(img, (width, h)), [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def draw_hud(img, tower_id, tower, boxes, alarm, streak, offset_min, fps, uplink, raw):
    h, w = img.shape[:2]
    s = w / 1280
    font = cv2.FONT_HERSHEY_SIMPLEX
    if boxes:
        # Magnified inset of the strongest detection: early smoke is only a few pixels wide.
        x1, y1, x2, y2, _ = max(boxes, key=lambda b: b[4])
        side = int(max(x2 - x1, y2 - y1) * 2.5)
        side = max(side, int(160 * s))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        ax, ay = max(0, min(w - side, cx - side // 2)), max(0, min(h - side, cy - side // 2))
        crop = img[ay:ay + side, ax:ax + side].copy()
        iw = int(340 * s)
        inset = cv2.resize(crop, (iw, iw), interpolation=cv2.INTER_CUBIC)
        sc = iw / side
        cv2.rectangle(inset, (int((x1 - ax) * sc), int((y1 - ay) * sc)), (int((x2 - ax) * sc), int((y2 - ay) * sc)),
                      (40, 40, 255) if alarm else (0, 200, 255), max(2, int(2 * s)))
        px, py = w - iw - int(20 * s), h - iw - int(76 * s)
        img[py:py + iw, px:px + iw] = inset
        cv2.rectangle(img, (px, py), (px + iw, py + iw), (255, 255, 255), max(1, int(2 * s)))
        cv2.putText(img, "ZOOM", (px + int(10 * s), py + int(28 * s)), font, 0.6 * s,
                    (255, 255, 255), max(1, int(2 * s)), cv2.LINE_AA)

    for (x1, y1, x2, y2, conf) in boxes:
        color = (40, 40, 255) if alarm else (0, 200, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, max(2, int(3 * s)))
        label = f"SMOKE {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, font, 0.7 * s, max(1, int(2 * s)))
        cv2.rectangle(img, (x1, y1 - th - int(12 * s)), (x1 + tw + int(12 * s), y1), color, -1)
        cv2.putText(img, label, (x1 + int(6 * s), y1 - int(6 * s)), font, 0.7 * s, (0, 0, 0), max(1, int(2 * s)), cv2.LINE_AA)

    panel = img.copy()
    cv2.rectangle(panel, (0, 0), (w, int(54 * s)), (0, 0, 0), -1)
    cv2.addWeighted(panel, 0.55, img, 0.45, 0, img)
    t = f"T{offset_min:+d} min from ignition" if offset_min is not None else time.strftime("%H:%M:%S")
    left = f"{tower_id.upper()}  {tower['name']}   {t}"
    right = f"{fps:4.1f} FPS   MQTT up {uplink / 1024:6.1f} KB   video would be {raw / 1024 / 1024:6.1f} MB"
    cv2.putText(img, left, (int(16 * s), int(35 * s)), font, 0.75 * s, (255, 255, 255), max(1, int(2 * s)), cv2.LINE_AA)
    (rw, _), _ = cv2.getTextSize(right, font, 0.6 * s, max(1, int(1.5 * s)))
    cv2.putText(img, right, (w - rw - int(16 * s), int(35 * s)), font, 0.6 * s, (200, 200, 200), max(1, int(1.5 * s)), cv2.LINE_AA)

    if alarm:
        cv2.rectangle(img, (0, h - int(56 * s)), (w, h), (30, 30, 220), -1)
        cv2.putText(img, "ALARM  ->  published to MQTT  wildfire/" + tower_id + "/detection",
                    (int(16 * s), h - int(19 * s)), font, 0.8 * s, (255, 255, 255), max(1, int(2 * s)), cv2.LINE_AA)
    elif streak:
        msg = f"smoke candidate  {streak}/{config.CONSECUTIVE_FRAMES} frames"
        cv2.putText(img, msg, (int(16 * s), h - int(20 * s)), font, 0.7 * s, (0, 200, 255), max(1, int(2 * s)), cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tower", default="tower-01", choices=config.TOWERS)
    ap.add_argument("--source", required=True, help="frames folder, video file, webcam index or rtmp:// url")
    ap.add_argument("--fps", type=float, default=0, help="limit processing rate (replay speed for frame folders)")
    ap.add_argument("--save", help="write annotated H.264 video here")
    ap.add_argument("--show", action="store_true", help="show a live window")
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    tower = config.TOWERS[args.tower]
    status_topic = config.topic(args.tower, "status")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.tower)
    # Broker publishes this on our behalf if the node drops off the network.
    client.will_set(status_topic, json.dumps({"state": "offline"}), qos=1, retain=True)
    client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=10)
    client.loop_start()

    uplink = 0

    def publish(kind, payload, qos=0, retain=False):
        nonlocal uplink
        data = json.dumps(payload)
        client.publish(config.topic(args.tower, kind), data, qos=qos, retain=retain)
        uplink += len(data)

    publish("status", {"state": "online", "tower": tower, "ts": time.time()}, qos=1, retain=True)

    model = YOLO(config.MODEL_PATH)
    writer = None
    tmp_path = None
    streak, alarms, frames, raw = 0, 0, 0, 0
    last_alarm = -1e9
    alarm_frames_left = 0
    started = last_hb = time.time()
    fps = 0.0

    for frame, offset in frame_source(args.source):
        t0 = time.time()
        h, w = frame.shape[:2]
        # What a camera would push upstream if it streamed video instead of events.
        raw += len(jpeg_bytes(frame, min(w, 1920), 80))

        r = model.predict(frame, imgsz=config.IMG_SIZE, conf=config.CONF_THRESHOLD, iou=0.01,
                          device=args.device, verbose=False)[0]
        boxes = [(*map(int, b.xyxy[0].tolist()), float(b.conf)) for b in r.boxes]
        streak = streak + 1 if boxes else 0

        alarm_now = False
        if streak >= config.CONSECUTIVE_FRAMES and time.time() - last_alarm > config.ALARM_COOLDOWN_S:
            best = max(boxes, key=lambda b: b[4])
            cx = (best[0] + best[2]) / 2
            alarm_now, alarms, last_alarm, alarm_frames_left = True, alarms + 1, time.time(), 12

        frames += 1
        dt = time.time() - t0
        fps = 0.9 * fps + 0.1 * (1 / max(dt, 1e-3)) if frames > 1 else 1 / max(dt, 1e-3)

        draw_hud(frame, args.tower, tower, boxes, alarm_frames_left > 0, streak, offset, fps, uplink, raw)
        alarm_frames_left = max(0, alarm_frames_left - 1)

        if alarm_now:
            snapshot = jpeg_bytes(frame, 960, 75)
            publish("detection", {
                "tower_id": args.tower,
                "ts": time.time(),
                "confidence": round(best[4], 3),
                "bbox": [round(best[0] / w, 4), round(best[1] / h, 4), round(best[2] / w, 4), round(best[3] / h, 4)],
                "azimuth_deg": round(azimuth_deg(cx, w, tower), 2),
                "frames_confirmed": streak,
                "ignition_offset_min": offset,
                "snapshot_jpeg_b64": base64.b64encode(snapshot).decode(),
            }, qos=1)
            print(f"[{args.tower}] ALARM conf={best[4]:.2f} az={azimuth_deg(cx, w, tower):.1f} "
                  f"offset={offset} min, event {len(snapshot) / 1024:.0f} KB")

        if time.time() - last_hb > 3:
            publish("heartbeat", {"fps": round(fps, 1), "frames": frames, "alarms": alarms,
                                  "uplink_bytes": uplink, "video_equiv_bytes": raw,
                                  "uptime_s": int(time.time() - started)})
            last_hb = time.time()

        if args.save:
            out = cv2.resize(frame, (1280, int(h * 1280 / w)))
            if writer is None:
                tmp_path = args.save + ".tmp.mp4"
                writer = cv2.VideoWriter(tmp_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                         args.fps or 25, (out.shape[1], out.shape[0]))
            writer.write(out)
        if args.show:
            cv2.imshow(args.tower, cv2.resize(frame, (1280, int(h * 1280 / w))))
            if cv2.waitKey(1) & 0xFF == 27:
                break
        if args.fps:
            time.sleep(max(0, 1 / args.fps - (time.time() - t0)))

    publish("heartbeat", {"fps": round(fps, 1), "frames": frames, "alarms": alarms,
                          "uplink_bytes": uplink, "video_equiv_bytes": raw, "uptime_s": int(time.time() - started)})
    client.publish(status_topic, json.dumps({"state": "offline"}), qos=1, retain=True).wait_for_publish()
    client.disconnect()  # clean disconnect: the broker discards the Last Will
    client.loop_stop()
    if writer is not None:
        writer.release()
        import imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", tmp_path,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", args.save],
                       check=True)
        os.remove(tmp_path)
    print(f"[{args.tower}] done: {frames} frames, {alarms} alarms, MQTT uplink {uplink / 1024:.1f} KB "
          f"vs {raw / 1024 / 1024:.1f} MB of video")


if __name__ == "__main__":
    main()
