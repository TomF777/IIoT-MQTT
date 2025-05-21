"""
Script reads acceleration data from vibration sensor over MQTT,
calculates anomalies using z-score method and stores results in InfluxDB
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
logger = logging.getLogger(__name__)


def get_env_var(
    env_var: str, req_type=None, default: str | int | float = None
) -> str | int | float:
    """Read env variable and return its required value with log information

    Args:
        env_var (str): Name of environment variable
        req_type (str, int, float): required data type of env variable.
        default (str, int, float): will be returned if is set and env variable does not exist

    Raises:
        SystemExit: Stop program if set type_var has not passed validate
        SystemExit: Stop program if env var does not exist and default is not set
        SystemExit: Stop program if cannot convert env var variable to req_type
    """
    # set local variable. Type and value of read env variable
    env_type = type(env_var)
    env_val = os.getenv(env_var, None)

    # check if input convert type is correct or it is None (if not, return error and stop program)
    allow_convert = [str, int, float]
    if req_type not in allow_convert and req_type is not None:
        logger.error(
            "Cannot convert value of env_var %s to %s. \
                Allowed convert type: str, int, float",
                env_var, req_type
        )
        raise SystemExit

    # Return value of env variable
    if env_val is None and default is None:
        # env_var does not exist and we did not set default value
        logger.error("Env variable %s does not exist",
                     env_var)
        raise SystemExit
    elif env_val is None:
        # env_var does not exist but return default (default is different than none)
        logger.warning(
            "Env variable %s does not exist, return default value: %s",
            env_var, default
        )
        return default
    elif env_type is not req_type and req_type is not None:
        # env var exists and it's type is diffrent as configured
        try:
            converted_env = req_type(env_val)
            logger.info(
                "Env variable %s value: %s. Converted from %s to %s.",
                env_var, env_val, env_type, req_type
            )
            return converted_env
        except Exception as e:
            logger.error(
                "Convert env_var variable %s from %s to %s failed: %s",
                env_var, env_type, req_type, e
            )
            raise SystemExit
    else:
        # env_var exists, is the same type (or we not set type)
        logger.info("Env variable %s value: %s, type: %s",
                    env_var, env_val, env_type)
        return env_val



# Assignment const variable from env var or created using env var
logger.info("Setting const global variables")

LINE_NAME = get_env_var("LINE_NAME", str)
MACHINE_NAME = get_env_var("MACHINE_NAME", str)
SENSOR_NAME = get_env_var("SENSOR_NAME", str)

MQTT_USERNAME = get_env_var("MQTT_USERNAME", str)
MQTT_PASSWORD = get_env_var("MQTT_PASSWORD", str)
MQTT_HOST = get_env_var("MQTT_HOST", str)
MQTT_PORT = get_env_var("MQTT_PORT", int)
MQTT_QOS = get_env_var("MQTT_QOS", int)
MQTT_TOPIC = LINE_NAME + "/" + MACHINE_NAME + "/" + SENSOR_NAME
logger.info("MQTT_TOPIC value is: %s", MQTT_TOPIC)

INFLUX_HOST = get_env_var("INFLUX_HOST", str)
INFLUX_PORT = get_env_var("INFLUX_PORT", str)
INFLUX_BUCKET_NAME = get_env_var("INFLUX_BUCKET_NAME", str)
INFLUX_BATCH_SIZE = get_env_var("INFLUX_BATCH_SIZE", int)
INFLUX_FLUSH_INTERVAL = get_env_var("INFLUX_FLUSH_INTERVAL", int)
INFLUX_JITTER_INTERVAL = get_env_var("INFLUX_JITTER_INTERVAL", int)
INFLUX_ORG = get_env_var("INFLUX_ORG", str)
INFLUX_TOKEN = get_env_var("INFLUX_TOKEN", str)
INFLUX_URL = "http://" + INFLUX_HOST + ":" + INFLUX_PORT
logger.info("INFLUX_URL value is:  %s", INFLUX_URL)

#Threshold for z-score value. Point above this threshold is treated as anomaly
Z_SCORE_THRESHOLD = get_env_var("Z_SCORE_THRESHOLD", float, default=2.0)

#Number of model points in list to calculate anomaly
MODEL_WINDOW_SIZE = get_env_var("MODEL_WINDOW_SIZE", int, default=100)

#Number of anomaly point in list to calculate anomaly ration
ANOMALY_LIST_SIZE = get_env_var("ANOMALY_LIST_SIZE", int, default=100)


class AnomalyDetectionZscore:
    """
        Analyse real-time data from electrical device
        and apply z-score algorithm to detect anomalies

        model_data          list where real-time (non anomalous) data are stored
        model_size          definition how many data points should be in `model_data`
        anomaly_list        list with anomaly detection results (1 and 0)
        anomaly_list_size  definition how many data points should be in `anomaly_list`
        anomaly_ratio       percentage of anomalous data in `anomaly_list`
        anomaly             result if current data point is anomaly (1) or not (0)
        model_avg           avarage mean of `model_data`
        model_std_dev       standard deviation of `model_data`
        z_score             calculated z-score value for single sensor data
        z_score_thresh      threshold above which sensor data is interpeted as anomalous
        name                name of the object/sensor on which the algorithm is applied
    """

    def __init__(self, name: str,
                 model_size: int, 
                 anomaly_list_size: int, 
                 logger) -> None:
        self._model_data = []
        self._model_size = model_size
        self._anomaly_list = []
        self._anomaly_list_size = anomaly_list_size
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._z_score = 0.0
        self._z_score_thresh = 0.0
        self._name = name
        self._logger = logger

    # Read only wariables
    @property
    def anomaly(self) -> int:
        """return 1 if data point is anmaly, 0 else"""
        return self._anomaly

    @property
    def model_avg(self) -> float:
        """return Mean of sensor data from given data model"""
        return self._model_avg

    @property
    def model_std_dev(self) -> float:
        """return Std Dev of sensor data from given data model"""
        return self._model_std_dev

    @property
    def z_score(self) -> float:
        """return calculated z-score value for given sensor data point"""
        return self._z_score

    @property
    def anomaly_ratio(self) -> float:
        """return anomaly ratio in real-time data"""
        return self._anomaly_ratio

    @property
    def model_completeness(self) -> int:
        """return percentage of data model"""
        return int(100 * len(self._model_data) / self._model_size)

    @property
    def z_score_thresh(self) -> float:
        """return z-score threshold value"""
        return self._z_score_thresh

    @z_score_thresh.setter
    def z_score_thresh(self, z_score_threshold: float):
        if z_score_threshold == 0:
            logger.error("Z-score threshold must be above zero")
            self._z_score_thresh = 2.0
        else:
            self._z_score_thresh = z_score_threshold

    def reset_algorithm(self) -> bool:
        """Reset data model in algorithm"""

        self._model_data = []
        self._anomaly_list = []
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._z_score = 0.0

    def is_model_complete(self) -> bool:
        """Return True if data model has enough data points"""
        return True if len(self._model_data) == self._model_size else False

    def calculate_anomaly_ratio(self):
        """Sum all anomalies results (0 and 1) from `anomaly_list`
           and divide it by the size of the list

        Args:
            anomaly_list_size (int): size of anomaly list to calculate ratio
        """

        try:
            if self.is_model_complete():
                if len(self._anomaly_list) < self._anomaly_list_size:
                    self._anomaly_list.append(self._anomaly)
                else:
                    self._anomaly_list.pop(0)
                    self._anomaly_list.append(self._anomaly)
                    self._anomaly_ratio = round(sum(self._anomaly_list) / self._anomaly_list_size, 3)
        except Exception as e:
            logger.error(
                "Calculation `anomaly ratio of model` %s failed. \
                    Error code/reason: %s", self._name, e
            )

    def check_if_anomaly(self, value: float):
        """
        Z-score algorithm to check if argument value is anomaly or not.

        Args:
            value (any): input value (sensor data) to be evaluated by algorithm
        """

        try:
            if self.is_model_complete():
                # recalculate the avg and std dev using only data points which are not anomaly
                self._model_avg = round(abs(statistics.mean(self._model_data)), 3)
                self._model_std_dev = abs(statistics.stdev(self._model_data))

                # avoid division by zero
                if self._model_std_dev == 0:
                    self._model_std_dev = 0.001
                self._z_score = round((abs(value) - self._model_avg) / self._model_std_dev, 3)

                # Check if new point is beyond z-score threshold i.e. this is anomaly
                if abs(self._z_score) > self.z_score_thresh:
                    # If anomaly, do not add to the model_data
                    self._anomaly = 1
                else:
                    # If not anomaly, add this point to data model
                    # and delete the 1st point (moving window)
                    self._model_data.pop(0)
                    self._model_data.append(value)
                    self._anomaly = 0

            else:
                # build data model by appending incoming sensor data to the list `model_data`
                self._model_data.append(value)

        except Exception as e:
            logger.error(
                'Calculation `anomaly of model` %s failed. \
                    Error code/reason: %s', self._name, e
            )


def on_connect(mqttclient, userdata, flags, rc, properties):
    """Method triggered by mqtt on connect callback and log information about status of connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        flags: response flags sent by the broker
        rc: the connection result code
    """
    if rc == 0:
        logger.info("Connection to MQTT Broker sucesfull. Result Code: 0")
    elif rc == 1:
        logger.warning(
            "Connection to MQTT Broker refused - incorrect protocol version. Result Code: 1}"
        )
    elif rc == 2:
        logger.warning(
            "Connection to MQTT Broker refused - invalid client identifier. Result Code: 2"
        )
    elif rc == 3:
        logger.warning(
            "Connection to MQTT Broker refused – server unavailable. Result Code: 3"
        )
    elif rc == 4:
        logger.warning(
            "Connection to MQTT Broker refused – bad username or password. Result Code: 4"
        )
    elif rc == 5:
        logger.warning(
            "Connection to MQTT Broker refused – not authorised. Result Code: 5"
        )
    else:
        logger.warning("Conection problem (unknown result code). Result Code: %s", rc)


def on_disconnect(mqttclient, userdata, rc, properties):
    """Method triggered by mqtt on disconnect callback and log information about lost connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        rc: the connection result code
    """
    logger.info("Lost conection with MQTT Broker. Result Code: %s", rc)


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
    # Extract received mqtt data
    data = message.payload.decode("utf-8")
    mqtt_data = json.loads(data)

    try:
        sensor_name = mqtt_data["SensorName"]
        vib_accel_tot_rms_x = float(mqtt_data["VibAccelTotRmsX"])
        vib_accel_tot_rms_y = float(mqtt_data["VibAccelTotRmsY"])
        vib_accel_tot_rms_z = float(mqtt_data["VibAccelTotRmsZ"])
    except Exception as e:
        logger.error("No valid sensor data in json included")
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

    # Anomaly detection of vibration sensor
    vib_sensor_analytics.z_score_thresh = Z_SCORE_THRESHOLD
    vib_sensor_analytics.check_if_anomaly(vib_total_rms)
    vib_sensor_analytics.calculate_anomaly_ratio()

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
            .field("anomaly", int(vib_sensor_analytics.anomaly))
            .field("anomaly_ratio", round(float(vib_sensor_analytics.anomaly_ratio), 4))
            .field("model_avg", round(float(vib_sensor_analytics.model_avg), 4))
            .field("z_score", round(float(vib_sensor_analytics.z_score), 4))
            .field("z_score_thresh", round(float(vib_sensor_analytics.z_score_thresh), 4))
            .time(
                time=datetime.fromtimestamp(int(mqtt_data["TimeStamp"]) / 1000, UTC),
                write_precision="ms",
            )
        )

        with influx_client.write_api(write_options=write_options) as write_api:
            write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

    except Exception as e:
        logger.error("Send data to InfluxDB failed. Error code/reason: %s", e)


# Main function of script
if __name__ == "__main__":

    # Creating vibration sensor anomaly object
    vib_sensor_analytics = AnomalyDetectionZscore("vibration_analytics", 
                                        MODEL_WINDOW_SIZE, 
                                        ANOMALY_LIST_SIZE, 
                                        logger)

    # Configuring conection with InfluxDB database
    try:
        logger.info("Configuring InfluxDB client ")
        influx_client = influxdb_client.InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, enable_gzip=False
        )

        logger.info("Configuring InfluxDB write api")
        write_options = WriteOptions(batch_size=INFLUX_BATCH_SIZE,
                                     flush_interval=INFLUX_FLUSH_INTERVAL,
                                     jitter_interval=INFLUX_JITTER_INTERVAL,
                                     retry_interval=1000)

    except Exception as e:
        logger.error("Configuring InfluxDB failed. Error code/reason: %s", e)

    # Configuring MQTT connection and subscribe topic
    try:
        logger.info("Configuring MQTT")
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        mqtt_client.connect(MQTT_HOST, MQTT_PORT)
        mqtt_client.subscribe(MQTT_TOPIC, MQTT_QOS)
    except Exception as e:
        logger.error("Configuring MQTT failed. Error code/reason: %s", e)

    mqtt_client.loop_forever()
