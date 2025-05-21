import time
import json
import random
from datetime import datetime, timezone
from threading import Thread
from paho.mqtt import client as mqtt_client

MQTT_USER = "mqttbroker"
MQTT_PASSWORD = "IoT-mqttbroker"

class MqttClient():

    def __init__(self, client_id, broker, port):
        """
        simple mqtt client
        """
        self.client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2,
                                        client_id, protocol=mqtt_client.MQTTv5)
        self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(broker, port)
        self.read_topic = None
        self.read_payload = None

    def on_message(self, client, userdata, message):
        """mqtt message received"""
        print(message.topic, "  ", message.payload)

    def on_connect(self, mqttc, userdata, flags, rc, props):
        """mqtt client connected to broker"""
        if rc == 0:
            print(" Connected to MQTT Broker")
        else:
            print(f" Failed to connect to MQTT Broker, error code: {rc}")
            if rc==1:
                print("1: Connection refused - incorrect protocol version")
            elif rc==2:
                print("2: Connection refused - invalid client identifier")
            elif rc==3:
                print("3: Connection refused - server unavailable")
            elif rc==4:
                print("4: Connection refused - bad username or password")
            elif rc==5:
                print("5: Connection refused - not authorised")
        time.sleep(2)

    def start(self):
        self.client.loop_start
    def publish_message(self, topic, json):
        self.client.publish(topic, json)

    def read_message(self):
        return self.read_topic, self.read_payload

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()

def generic_sensor_sim(sensor_value, interval, mqtt_client, topic):

    sensor_mean = sensor_value

    while True:
        line_name = topic.split("/")[0]
        machine_name = topic.split("/")[1]
        sensor_name = topic.split("/")[2]

        offset = random.uniform(-7, 7)
        sensor_value = sensor_mean + offset

        # unix time stamp with ms resolution
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)

        json_send = { "LineName":line_name, "MachineName":machine_name, "SensorName":sensor_name,
                     "SensorValue": round(sensor_value, 2),
                     "TimeStamp":timestamp}
        mqtt_client.publish_message(topic, json.dumps(json_send))
        print("generic sensor json sent")
        time.sleep(interval)

def vib_sim(avg_vib_level, interval, mqtt_client, topic):

    while True:
        line_name = topic.split("/")[0]
        machine_name = topic.split("/")[1]
        sensor_name = topic.split("/")[2]

        number = random.randint(1, 5)
        number_x = random.randint(1, 5)
        number_y = random.randint(1, 5)
        number_z = random.randint(1, 5)
        vib_level = avg_vib_level - 2.5 + number
        vib_level_x = avg_vib_level - 2.5 + number_x
        vib_level_y = avg_vib_level - 2.5 + number_y
        vib_level_z = avg_vib_level - 2.5 + number_z
        # unix time stamp with ms resolution
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        json_send = { "LineName":line_name, "MachineName":machine_name, "SensorName":sensor_name,
                     "VibrationLevel": vib_level,
                     "VibAccelTotal_RMS_X": vib_level_x,
                     "VibAccelTotal_RMS_Y": vib_level_y,
                     "VibAccelTotal_RMS_Z": vib_level_z,
                     "TimeStamp":timestamp}
        mqtt_client.publish_message(topic, json.dumps(json_send))
        print("vib json sent")
        time.sleep(interval)

def temp_humid_sim_1(avg_temp_level, avg_humid_level, mqtt_client, topic):

    while True:
        line_name = topic.split("/")[0]
        machine_name = topic.split("/")[1]
        sensor_name = topic.split("/")[2]

        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        temp_level = avg_temp_level - 2 + num1 * 0.1
        humid_level = avg_humid_level - 10 + num2
        # unix time stamp with ms resolution
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        json_send = { "LineName":line_name,
                      "MachineName":machine_name,
                      "SensorName":sensor_name,
                      "Temperature": temp_level,
                      "Humidity": humid_level,
                      "TimeStamp":timestamp}

        mqtt_client.publish_message(topic, json.dumps(json_send))
        print("temp/humid json sent")
        time.sleep(1)

#mqtt_client = MqttClient("IoT_Industrial", "192.168.1.165", 1883)
mqtt_client = MqttClient("IoT_Industrial", "localhost", 1883)
mqtt_client.start()

# publish data with topic structure: <line_name>/<machine_name>/<sensor_name>
thread_vib_sim_1 = Thread(target=vib_sim, name="thread_vib_sim_1",
                          args = (25, 1, mqtt_client, "IoT_Industrial/device01/Vib1" ))
thread_vib_sim_2 = Thread(target=vib_sim, name="thread_vib_sim_2",
                          args = (30, 0.2, mqtt_client, "IoT_Industrial/device01/Vib2" ))
thread_vib_sim_3 = Thread(target=vib_sim, name="thread_vib_sim_3",
                          args = (30, 2, mqtt_client, "IoT_Industrial/device01/Vib3" ))
thread_vib_sim_4 = Thread(target=vib_sim, name="thread_vib_sim_4",
                          args = (40, 1, mqtt_client, "IoT_Industrial/device01/Vib4" ))
thread_vib_sim_5 = Thread(target=vib_sim, name="thread_vib_sim_5",
                          args = (55, 1.5, mqtt_client, "IoT_Industrial/device01/Vib5" ))

thread_temp_humid_sim_1 = Thread(target=temp_humid_sim_1, name="thread_temp_humid_sim_1",
                                 args = (24, 50, mqtt_client, "IoT_Industrial/device01/TempHumid1" ))


thread_generic_sensor_1 = Thread(target=generic_sensor_sim, name="thread_generic_sensor_1",
                                 args= (15, 2, mqtt_client, "IoT_Industrial/device01/Sensor1"))

thread_generic_sensor_2 = Thread(target=generic_sensor_sim, name="thread_generic_sensor_2",
                                 args= (5, 2, mqtt_client, "IoT_Industrial/device01/Sensor2"))

thread_generic_sensor_3 = Thread(target=generic_sensor_sim, name="thread_generic_sensor_3",
                                 args= (20, 2, mqtt_client, "IoT_Industrial/device01/Sensor3"))

thread_vib_sim_1.start()
thread_vib_sim_2.start()
thread_vib_sim_3.start()
thread_vib_sim_4.start()
thread_vib_sim_5.start()
thread_temp_humid_sim_1.start()
thread_generic_sensor_1.start()
thread_generic_sensor_2.start()
thread_generic_sensor_3.start()

