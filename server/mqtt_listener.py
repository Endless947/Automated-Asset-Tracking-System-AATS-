import json
from typing import Callable

import paho.mqtt.client as mqtt


class MQTTListener:
    def __init__(
        self,
        broker: str,
        port: int,
        on_status: Callable[[dict], None],
        on_event: Callable[[dict], None],
    ) -> None:
        self.broker = broker
        self.port = port
        self.on_status = on_status
        self.on_event = on_event

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Server connected to MQTT broker")
            client.subscribe("aats/lab/+/pc/+/status", qos=1)
            client.subscribe("aats/lab/+/pc/+/event", qos=1)
        else:
            print("Server MQTT connection failed:", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        if msg.topic.endswith("/status"):
            self.on_status(payload)
        elif msg.topic.endswith("/event"):
            self.on_event(payload)

    def start(self) -> None:
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
