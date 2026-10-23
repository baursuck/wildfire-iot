"""Simulated weather station on each tower. Real stations report over NB-IoT every 10 minutes;
here the period is shortened for the demo. Payload keys are short on purpose: NB-IoT uplinks are tiny."""
import argparse
import json
import random
import time

import paho.mqtt.client as mqtt

import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, default=5, help="seconds between reports (real deployment: 600)")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wx-gateway")
    client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    client.loop_start()

    # Hot dry afternoon in the foothills: noise that keeps pulling back to these values.
    base = {tid: {"t": 31.0 + i, "rh": 19.0 - i * 2, "ws": 5.5 + i} for i, tid in enumerate(config.TOWERS)}
    state = {tid: {**b, "wd": 250.0 + i * 15, "bat": 3.95 - i * 0.03} for i, (tid, b) in enumerate(base.items())}
    while True:
        for tid, s in state.items():
            b = base[tid]
            s["t"] += 0.1 * (b["t"] - s["t"]) + random.uniform(-0.2, 0.2)
            s["rh"] = min(60, max(8, s["rh"] + 0.1 * (b["rh"] - s["rh"]) + random.uniform(-0.4, 0.4)))
            s["ws"] = max(0, s["ws"] + 0.1 * (b["ws"] - s["ws"]) + random.uniform(-0.6, 0.6))
            s["wd"] = (s["wd"] + random.uniform(-6, 6)) % 360
            s["bat"] = max(3.3, s["bat"] - 0.0005)
            payload = {"t": round(s["t"], 1), "rh": round(s["rh"]), "ws": round(s["ws"], 1),
                       "wd": round(s["wd"]), "bat": round(s["bat"], 2), "rssi": random.randint(-104, -92)}
            client.publish(config.topic(tid, "weather"), json.dumps(payload, separators=(",", ":")), qos=0, retain=True)
        time.sleep(args.period)


if __name__ == "__main__":
    main()
