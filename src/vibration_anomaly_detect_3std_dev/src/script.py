"""
    Script reads vibration value over from MQTT,
    calculates anomaly using +- 3 std dev method and store results to InfluxDB
"""
import os
import json
import logging
import statistics
import math
from datetime import datetime, UTC
import paho.mqtt.client as mqtt
import influxdb_client
from influxdb_client.client.write_api import WriteOptions



# Set loging system
LOG_FORMAT = "%(levelname)s %(asctime)s \
    Function: %(funcName)s \
    Line: %(lineno)d \
    Message: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger(__name__)


def get_para(
    env: str,
    req_type=None,
    default: str | int | float = None
) -> str | int | float:
    """Read env variable and return required value of it with log information

    Args:
        env (str): Name of environement variable
        req_type (str, int, float): type of returned env variable.
        default (str, int, float): will be returned if is set and env variable does not exist

    Raises:
        SystemExit: Stop program if set type_var has not passed validate
        SystemExit: Stop program if env does not exist and default is not set
        SystemExit: Stop program if cannot convert env variable to req_type
    """
    # set local variable. Type and value of readed env variable
    env_type = type(env)
    env_val = os.getenv(env, None)

    # check if input convert type is correct or is None (if not, return error and stop program)
    allow_convert = [str, int, float]
    if req_type not in allow_convert and req_type is not None:
        LOGGER.error(
            f"Cannot convert value of env {env} to {req_type}. \
                Allowed convert type: str, int, float"
        )
        raise SystemExit

    # Return value of env variable
    if env_val is None and default is None:
        # env does not exist and we did not set default value
        LOGGER.error(f"Env variable {env} does not exist")
        raise SystemExit
    elif env_val is None:
        # env does not exist but return default (default is different than none)
        LOGGER.warning(
            f"Env variable {env} does not exist, return default value: {default}"
        )
        return default
    elif env_type is not req_type and req_type is not None:
        # env var exist and it's type is diffrent than what we set
        try:
            converted_env = req_type(env_val)
            LOGGER.info(
                f"Env variable {env} value: {env_val}. Converted from {env_type} to {req_type}."
            )
            return converted_env
        except Exception as e:
            LOGGER.error(
                f"Convert env variable {env} from {env_type} to {req_type} failed: {e}"
            )
            raise SystemExit
    else:
        # env exist, is the same type (or we not set type) so we return it
        LOGGER.info(f"Env variable {env} value: {env_val}, type: {env_type}")
        return env_val


# Assignment const variable from env or created using env
LOGGER.info("Seting const global variables")

LINE_NAME = get_para("LINE_NAME", str)
MACHINE_NAME = get_para("MACHINE_NAME", str)
SENSOR_NAME = get_para("SENSOR_NAME", str)

MQTT_USERNAME = get_para("MQTT_USERNAME", str)
MQTT_PASSWORD = get_para("MQTT_PASSWORD", str)
MQTT_HOST = get_para("MQTT_HOST", str)
MQTT_PORT = get_para("MQTT_PORT", int)
MQTT_QOS = get_para("MQTT_QOS", int)
MQTT_TOPIC = LINE_NAME + "/" + MACHINE_NAME + "/" + SENSOR_NAME
LOGGER.info(f"MQTT_TOPIC value is: {MQTT_TOPIC} ")

INFLUX_HOST = get_para("INFLUX_HOST", str)
INFLUX_PORT = get_para("INFLUX_PORT", str)
INFLUX_BUCKET_NAME = get_para("INFLUX_BUCKET_NAME", str)
INFLUX_BATCH_SIZE = get_para("INFLUX_BATCH_SIZE", int)
INFLUX_FLUSH_INTERVAL = get_para("INFLUX_FLUSH_INTERVAL", int)
INFLUX_JITTER_INTERVAL = get_para("INFLUX_JITTER_INTERVAL", int)
INFLUX_ORG = get_para("INFLUX_ORG", str)
INFLUX_TOKEN = get_para("INFLUX_TOKEN", str)
INFLUX_URL = "http://" + INFLUX_HOST + ":" + INFLUX_PORT
LOGGER.info(f"INFLUX_URL value is:  {INFLUX_URL} ")

#Value used to calculate upper_thresh and lower_thresh when std dev is below set limit
THRESH_STD_LIMIT =  get_para("THRESH_STD_LIMIT", int, default=20)

#Number of model points in list to calculate anomaly
MODEL_WINDOW_SIZE = get_para("MODEL_WINDOW_SIZE", int, default=100)

#Number of anomaly point in list to calculate anomaly ratio
ANOMALY_LIST_SIZE = get_para("ANOMALY_LIST_SIZE", int, default=100)

class AnomalyDetection:
    """
        Analyse real-time data from sensor
        and apply +-3 std dev algorithm to detect anomalies

        model_data          list where real-time (non anomalous) data are stored
        model_size          definition how many data points should be in `model_data`
        anomaly_list        list with anomaly detection results (1 and 0)
        anomaly_ratio       percentage of anomalous data in `anomaly_list`
        anomaly             result if current data point is anomaly (1) or not (0)
        model_avg           avarage mean of `model_data`
        model_std_dev       standard deviation of `model_data`
        u_thresh            calculated positive limit above which data is treated as anomaly
        l_thresh            calculated negative limit below which data is treated as anomaly
        name                name of the object/sensor on which the algorithm is applied

    """

    # Init function
    def __init__(self, name: str, model_size: int, logger) -> None:
        self._model_data = []
        self._model_size = model_size
        self._anomaly_list = []
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._u_thresh = 0.0
        self._l_thresh = 0.0
        self._name = name
        self._logger = logger

    # Read only wariables
    @property
    def anomaly(self) -> int:
        """return 1 if data point is anmaly, 0 else"""
        return self._anomaly

    @property
    def model_avg(self):
        """return Mean of sensor data from given data model"""
        return self._model_avg

    @property
    def model_std_dev(self):
        """return Std Dev of sensor data from given data model"""
        return self._model_std_dev

    @property
    def anomaly_ratio(self):
        """return anomaly ratio in real-time data"""
        return self._anomaly_ratio

    @property
    def model_completeness(self) -> int:
        """return percentage of data model"""
        return int(100 * len(self._model_data) / self._model_size)

    def reset_algorithm(self) -> bool:
        """Reset data model in algorithm"""

        self._model_data = []
        self._anomaly_list = []
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0

    def is_model_complete(self) -> bool:
        """Return True if data model has enough data points"""
        return True if len(self._model_data) == self._model_size else False


    def calculate_anomaly_ratio(self, anomaly_list_size: int):
        """Sum all anomalies results (0 and 1) from `anomaly_list`
           and divide it by the size of the list

        Args:
            anomaly_list_size (int): size of anomaly list to calculate ratio
        """
        try:
            if not self.is_model_complete():
                pass
            elif len(self._anomaly_list) < anomaly_list_size:
                self._anomaly_list.append(self._anomaly)
            else:
                self._anomaly_list.pop(0)
                self._anomaly_list.append(self._anomaly)
                self._anomaly_ratio = round(sum(self._anomaly_list) / anomaly_list_size, 3)
        except Exception as e:
            self._logger.error(
                f"Calculation anomaly ratio of model {self._name} failed. \
                  Error code/reason: {e}"
            )

    def check_if_anomaly(self, value, limit: int = 0):
        """ +- 3 * std dev algorithm to check if argument value is anomaly or not.

        Args:
            value (any): input value to evaluate by algorithm

            limit (int): limit to avoid get to small u_thresh and l_thresh.
            Example: if input value is a time, and std dev is lower
                than data time resolution all next data points will be anomalous.
        """

        try:
            if self.is_model_complete():
                # recalculate the avg and std dev using only data points which are not anomaly
                self._model_avg = statistics.mean(self._model_data)
                self._model_std_dev = statistics.stdev(self._model_data)

                # calculate low and high limit
                if self._model_std_dev < limit and limit > 0:
                    # protect system to avoid situation when std dev lower then resolution time
                    self._u_thresh = self._model_avg + THRESH_STD_LIMIT
                    self._l_thresh = self._model_avg - THRESH_STD_LIMIT
                else:
                    # Use +- 3 std dev rule to calculate low and high limit
                    self._u_thresh = self._model_avg + 3 * self._model_std_dev
                    self._l_thresh = self._model_avg - 3 * self._model_std_dev

                # Check if new point is anomaly (is out of limit)
                if value >= self._l_thresh and value <= self._u_thresh:
                    # Point is not anomaly, remove oldest point
                    # from model and add new one at the end
                    self._model_data.pop(0)
                    self._model_data.append(value)
                    self._anomaly = 0
                else:
                    # If anomaly, do not add to the model_data
                    self._anomaly = 1

            else:
                # build data model by appending incoming sensor data to the list `model_data`
                self._model_data.append(value)

        except Exception as e:
            self._logger.error(
                f'Calculation anomaly of model "{self._name}" failed. Error code/reason: {e}'
            )


# Function trigered when connect to MQTT Broker
def on_connect(mqttclient, userdata, flags, rc, properties):
    """Method triggered by mqtt on connect callback and log information about status of connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        flags: response flags sent by the broker
        rc: the connection result code
    """
    if rc == 0:
        LOGGER.info("Connection to MQTT Broker sucesfull. Result Code: 0")
    elif rc == 1:
        LOGGER.warning(
            "Connection to MQTT Broker refused - incorrect protocol version. Result Code: 1}"
        )
    elif rc == 2:
        LOGGER.warning(
            "Connection to MQTT Broker refused - invalid client identifier. Result Code: 2"
        )
    elif rc == 3:
        LOGGER.warning(
            "Connection to MQTT Broker refused - server unavailable. Result Code: 3"
        )
    elif rc == 4:
        LOGGER.warning(
            "Connection to MQTT Broker refused - bad username or password. Result Code: 4"
        )
    elif rc == 5:
        LOGGER.warning(
            "Connection to MQTT Broker refused – not authorised. Result Code: 5"
        )
    else:
        LOGGER.warning(f"Conection problem (unknown result code). Result Code: {rc}")


# Function trigered when unexpect disconnect from MQTT Broker
def on_disconnect(mqttclient, userdata, rc, properties):
    """Method triggered by mqtt on disconnect callback and log information about lost connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        rc: the connection result code
    """
    LOGGER.info(f"Lost conection with MQTT Broker. Result Code: {rc}")


# Function trigered when message come to MQTT Broker
def on_message(mqttclient, userdata, message):
    """Method triggered when data apear on mqtt topic. Method is responisble for:
        1. Read acceleration data from mqtt broker
        2. Detect anomalys of total rms
        2. Send data to InfluxDB

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        message: data from MQTT topic
    """
    # extract received mqtt data
    data = message.payload.decode("utf-8")
    #data = data.replace("\u0000", "")
    mqtt_data = json.loads(data)

    try:
        sensor_name = mqtt_data["SensorName"]
        vib_accel_tot_rms_x = float(mqtt_data["VibAccelTotRmsX"])
        vib_accel_tot_rms_y = float(mqtt_data["VibAccelTotRmsY"])
        vib_accel_tot_rms_z = float(mqtt_data["VibAccelTotRmsZ"])
    except Exception as e:
        LOGGER.error("No valid sensor data in json included")
    else:

        # Calculating total rms
        vib_total_rms = round(
            float(
                math.sqrt(
                    vib_accel_tot_rms_x ** 2
                    + vib_accel_tot_rms_y ** 2
                    + vib_accel_tot_rms_z ** 2
                )
            ),
            5,
        )

        # Anomaly detection of vib sensor
        vib_sensor.check_if_anomaly(vib_total_rms)
        vib_sensor.calculate_anomaly_ratio(ANOMALY_LIST_SIZE)

        # Send data to InfluxDB
        try:
            measurement = ("VibSensor")

            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(mqtt_data["LineName"]))
                .tag("machine_name", str(mqtt_data["MachineName"]))
                .tag("sensor_name", sensor_name)
                .field("vib_accel_rms_x", round(vib_accel_tot_rms_x, 4))
                .field("vib_accel_rms_y", round(vib_accel_tot_rms_y, 4))
                .field("vib_accel_rms_z", round(vib_accel_tot_rms_z, 4))
                .field("vib_accel_rms_total", round(vib_total_rms, 4))
                .field("anomaly", int(vib_sensor.anomaly))
                .field("avg_window", round(float(vib_sensor.model_avg), 4))
                .field("std_window", round(float(vib_sensor.model_std_dev), 4))
                .field("anomaly_ratio", round(float(vib_sensor.anomaly_ratio), 4))
                .time(time=datetime.fromtimestamp(int(mqtt_data["TimeStamp"]) / 1000, UTC),
                    write_precision="ms",
                )
            )

            with influx_client.write_api(write_options=write_options) as write_api:
                write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

        except Exception as e:
            LOGGER.error(f"Send data to InfluxDB failed. Error code/reason: {e}")


# Main function of script
if __name__ == "__main__":

    # Create vibration sensor anomaly object
    vib_sensor = AnomalyDetection("vibration_anomaly", MODEL_WINDOW_SIZE, LOGGER)

    # Configuring conection with InfluxDB database
    try:
        LOGGER.info("Configuring InfluxDB client ")
        influx_client = influxdb_client.InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, enable_gzip=False
        )

        LOGGER.info("Configuring InfluxDB write api")
        write_options = WriteOptions(batch_size=INFLUX_BATCH_SIZE,
                                     flush_interval=INFLUX_FLUSH_INTERVAL,
                                     jitter_interval=INFLUX_JITTER_INTERVAL,
                                     retry_interval=1000)

    except Exception as e:
        LOGGER.error(f"Configuring InfluxDB failed. Error code/reason: {e}")

    # Configuring MQTT connection and subscribe topic
    try:
        LOGGER.info("Configuring MQTT")
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        mqtt_client.connect(MQTT_HOST, MQTT_PORT)
        mqtt_client.subscribe(MQTT_TOPIC, MQTT_QOS)
    except Exception as e:
        LOGGER.error(f"Configuring MQTT failed. Error code/reason: {e}")

    mqtt_client.loop_forever()
