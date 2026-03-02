import json
from typing import Any, Dict

import paho.mqtt.client as mqtt


class MQTTClient:
    def __init__(self, broker: str, port: int, lab_id: str, pc_id: str, agent_version: str) -> None:
        self.broker = broker
        self.port = port
        self.lab_id = lab_id
        self.pc_id = pc_id
        self.agent_version = agent_version

        self.topic_status = f"aats/lab/{lab_id}/pc/{pc_id}/status"
        self.topic_event = f"aats/lab/{lab_id}/pc/{pc_id}/event"

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        will_payload = {
            "lab_id": self.lab_id,
            "pc_id": self.pc_id,
            "pc_status": "offline",
            "last_seen": None,
            "agent_version": self.agent_version,
        }
        self.client.will_set(self.topic_status, json.dumps(will_payload), qos=1, retain=True)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker")
        else:
            print("Failed to connect, return code:", rc)

    def on_disconnect(self, client, userdata, rc):
        print("Disconnected from MQTT Broker")

    def connect(self) -> None:
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_event(self, payload: Dict[str, Any]) -> None:
        self.client.publish(self.topic_event, json.dumps(payload), qos=1, retain=False)

    def publish_status(self, payload: Dict[str, Any]) -> None:
        self.client.publish(self.topic_status, json.dumps(payload), qos=1, retain=True)
