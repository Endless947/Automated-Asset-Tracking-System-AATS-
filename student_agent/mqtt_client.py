import json
import time
import paho.mqtt.client as mqtt


class MQTTClient:
    def __init__(self, broker, port, lab_id, pc_id):
        self.broker = broker
        self.port = port
        self.lab_id = lab_id
        self.pc_id = pc_id

        self.topic_status = f"aats/lab/{lab_id}/{pc_id}/status"
        self.topic_heartbeat = f"aats/lab/{lab_id}/{pc_id}/heartbeat"

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker")
        else:
            print("Failed to connect, return code:", rc)

    def on_disconnect(self, client, userdata, rc):
        print("Disconnected from MQTT Broker")

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish_status(self, device, status, timestamp):
        message = {
            "lab_id": self.lab_id,
            "pc_id": self.pc_id,
            "device": device,
            "status": status,
            "timestamp": timestamp
        }

        self.client.publish(self.topic_status, json.dumps(message))

    def send_heartbeat(self):
        message = {
            "lab_id": self.lab_id,
            "pc_id": self.pc_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        self.client.publish(self.topic_heartbeat, json.dumps(message))
