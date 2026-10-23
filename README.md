# Wildfire IoT: early smoke detection on camera towers

KBTU IoT course project

Camera towers in the Ile-Alatau foothills near Almaty watch the slopes for smoke. Each tower runs a YOLO smoke detector next to the camera (edge computing) and sends only events over MQTT instead of streaming video. A backend collects the alarms, estimates the fire position from the tower bearings and sends a Telegram alert. A browser dashboard shows towers, alarms and weather in real time.

## How it works

| File | Role |
|---|---|
| `wildfire-iot/broker.py` | MQTT broker (amqtt): TCP 1883 for devices, WebSocket 9001 for the dashboard |
| `wildfire-iot/edge_node.py` | Tower edge node: reads frames (FIgLib folder, video, webcam or RTMP/RTSP stream), runs YOLO, publishes `status`, `heartbeat`, `detection` with a JPEG snapshot |
| `wildfire-iot/sensor_node.py` | Weather station: small NB-IoT style readings on `weather` |
| `wildfire-iot/backend.py` | Collects alarms, localises the fire from tower azimuths, sends Telegram alerts |
| `wildfire-iot/dashboard/` | Live web dashboard (MQTT over WebSocket) |
| `wildfire-iot/config.py` | Broker, topic tree `wildfire/<device>/<kind>`, tower positions and headings |
| `wildfire-iot/scripts/` | FIgLib download and detector evaluation |
| `presentation/` | Midterm slides, online: https://baursuck.github.io/wildfire-iot/ |

Offline towers are reported with the MQTT Last Will (`status = offline`).

## Run

```bash
cd wildfire-iot
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

# smoke detector: Pyronear YOLO11s (Apache-2.0)
.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('pyronear/yolo11s_sensitive-detector', local_dir='models/pyronear')"

# test video: HPWREN FIgLib fire sequences
./scripts/fetch_figlib.sh 20200911_FIRE_pi-s-mobo-c 20190610_FIRE_bh-w-mobo-c

# optional Telegram alerts: cp .env.example .env, put TELEGRAM_TOKEN there, then
.venv/bin/python telegram_setup.py

./run_demo.sh   # dashboard at http://localhost:8000
```

## Credits

- Smoke detector: [Pyronear](https://huggingface.co/pyronear/yolo11s_sensitive-detector), Apache-2.0.
- Fire image sequences: [HPWREN FIgLib](https://www.hpwren.ucsd.edu/FIgLib/), UC San Diego.
- Map imagery in the slides: Esri, Maxar, Earthstar Geographics.
