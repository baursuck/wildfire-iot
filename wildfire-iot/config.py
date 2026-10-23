"""Shared configuration for the wildfire IoT demo: broker, topics and tower metadata."""

MQTT_HOST = "localhost"
MQTT_PORT = 1883      # TCP listener for edge nodes and backend
MQTT_WS_PORT = 9001   # WebSocket listener for the browser dashboard

# Topic tree. Every device lives under wildfire/<device_id>/...
#   status     retained "online"/"offline" (offline is the broker-sent Last Will)
#   heartbeat  periodic health: fps, frames, uplink bytes, uptime
#   detection  smoke alarm: confidence, bbox, azimuth, JPEG snapshot (QoS 1)
#   weather    tower sensor readings, small NB-IoT style payload
TOPIC_ROOT = "wildfire"


def topic(device_id: str, kind: str) -> str:
    return f"{TOPIC_ROOT}/{device_id}/{kind}"


# Virtual towers in the Ile-Alatau foothills near Almaty. Video is replayed from HPWREN
# FIgLib tower cameras; positions and headings are a staged scenario for the localisation demo.
TOWERS = {
    "tower-01": {
        "name": "Kaskelen ridge",
        "lat": 43.1400, "lon": 76.7000,
        "heading_deg": 140.0,   # direction of the optical axis, clockwise from north
        "hfov_deg": 64.0,       # horizontal field of view of the camera
    },
    "tower-02": {
        "name": "Medeu",
        "lat": 43.1570, "lon": 77.0580,
        "heading_deg": 245.1,
        "hfov_deg": 64.0,
    },
}

# Detector and temporal filter
MODEL_PATH = "models/pyronear/best.pt"
IMG_SIZE = 1024
CONF_THRESHOLD = 0.20       # per-frame detection threshold
CONSECUTIVE_FRAMES = 3      # frames in a row with smoke before an alarm is raised
ALARM_COOLDOWN_S = 120      # do not repeat alarms from the same tower more often than this
