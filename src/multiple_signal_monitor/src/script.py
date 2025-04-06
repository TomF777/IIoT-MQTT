"""
    Catch data over mqtt from mutliple sensors
    and store its value and timestamp into InfluxDB.
    The script subscribes to 
    MachineName/LineName/# topic level and
    expects that sensor json data has 
    SensorName and SensorValue fields.
"""
import os
import json
import logging
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

# Geting parameters from env variable
def get_para(
    env: str, req_type=None, default: str | int | float = None
) -> str | int | float:
    """Function read env variable and return require value of it with log information

    Args:
        env (str): Name of enviromental variable
        req_type (str, int, float): define which type shoud have returned env variable.
        default (str, int, float): will be returnet if is set and env variable does not exist

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

MQTT_USERNAME = get_para("MQTT_USERNAME", str)
MQTT_PASSWORD = get_para("MQTT_PASSWORD", str)
MQTT_HOST = get_para("MQTT_HOST", str)
MQTT_PORT = get_para("MQTT_PORT", int)
MQTT_QOS = get_para("MQTT_QOS", int)
MQTT_TOPIC = LINE_NAME + "/" + MACHINE_NAME + "/#"
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


# Function trigered when connect to MQTT Broker
def on_connect(mqttclient, userdata, flags, rc, properties):
    """Method triggered by mqtt on connect callback and log information about status of connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        flags: response flags sent by the broker
        rc: the connection result code
        properties: properties
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
            "Connection to MQTT Broker refused - not authorised. Result Code: 5"
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
        properties: properties
    """
    LOGGER.info(f"Lost conection with MQTT Broker. Result Code: {rc}")


# Function trigered when message come to MQTT Broker
def on_message(mqttclient, userdata, message):
    """ Method called when data catched on mqtt topic.
        It reads payload sent over mqtt and
        store its content as line protocol into InfluxDB

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
        sensor_value = mqtt_data["SensorValue"]
        LOGGER.info(f"sensor name: {sensor_name}  sensor value: {sensor_value}")
    except Exception as e:
        LOGGER.error("No valid sensor data in json included")

    else:
        # Send data to InfluxDB
        try:
            measurement = ("GenericSensor")
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(mqtt_data["LineName"]))
                .tag("machine_name", str(mqtt_data["MachineName"]))
                .tag("sensor_name", sensor_name)
                .field("value", float(round(mqtt_data["SensorValue"], 4)))
                .time(time=datetime.fromtimestamp(int(mqtt_data["TimeStamp"]) / 1000, UTC),
                    write_precision='ms')
            )

            with influx_client.write_api(write_options=write_options) as write_api:
                write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

        except Exception as e:
            LOGGER.error(f"Send data to InfluxDB failed. Error code/reason: {e}")


# Main function of script
if __name__ == "__main__":

    # Configuring connection with InfluxDB database
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
