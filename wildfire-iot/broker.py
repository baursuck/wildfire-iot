"""Local MQTT broker (stand-in for Mosquitto on the server): TCP for devices, WebSocket for the dashboard."""
import asyncio
import logging

from amqtt.broker import Broker

from config import MQTT_PORT, MQTT_WS_PORT

BROKER_CONFIG = {
    "listeners": {
        "default": {"type": "tcp", "bind": f"0.0.0.0:{MQTT_PORT}"},
        "ws": {"type": "ws", "bind": f"0.0.0.0:{MQTT_WS_PORT}"},
    },
    "plugins": {
        "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
    },
}


async def main():
    broker = Broker(BROKER_CONFIG)
    await broker.start()
    print(f"MQTT broker up: tcp://0.0.0.0:{MQTT_PORT}  ws://0.0.0.0:{MQTT_WS_PORT}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
