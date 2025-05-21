"""
    Catch multiple states over mqtt 
    and store its value and timestamp into InfluxDB.
    The script subscribes to 
    MachineName/LineName/# topic level and
    expects that state json data has 
    'StateName' and 'StateValue' fields.
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
        logger.error("Env variable %s does not exist", env_var)
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


# Assignment const variable from env or created using env
logger.info("Setting const global variables")

LINE_NAME = get_env_var("LINE_NAME", str)
MACHINE_NAME = get_env_var("MACHINE_NAME", str)

MQTT_USERNAME = get_env_var("MQTT_USERNAME", str)
MQTT_PASSWORD = get_env_var("MQTT_PASSWORD", str)
MQTT_HOST = get_env_var("MQTT_HOST", str)
MQTT_PORT = get_env_var("MQTT_PORT", int)
MQTT_QOS = get_env_var("MQTT_QOS", int)
MQTT_TOPIC = LINE_NAME + "/" + MACHINE_NAME + "/#"
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
            "Connection to MQTT Broker refused - server unavailable. Result Code: 3"
        )
    elif rc == 4:
        logger.warning(
            "Connection to MQTT Broker refused - bad username or password. Result Code: 4"
        )
    elif rc == 5:
        logger.warning(
            "Connection to MQTT Broker refused - not authorised. Result Code: 5"
        )
    else:
        logger.warning("Conection problem (unknown result code). Result Code: %s", rc)


# Function trigered when unexpect disconnect from MQTT Broker
def on_disconnect(mqttclient, userdata, rc, properties):
    """Method triggered by mqtt on disconnect callback and log information about lost connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        rc: the connection result code
        properties: properties
    """
    logger.info("Lost conection with MQTT Broker. Result Code: %s", rc)


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
        state_name = mqtt_data["StateName"]
        state_value = mqtt_data["StateValue"]
        logger.info("state name: %s  sensor value: %s",
                    state_name, state_value)
    except Exception as e:
        logger.error("No valid sensor data in json included")

    else:
        # Send data to InfluxDB
        try:
            measurement = ("GenericState")
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(mqtt_data["LineName"]))
                .tag("machine_name", str(mqtt_data["MachineName"]))
                .tag("state_name", state_name)
                .field("value", int(mqtt_data["StateValue"]))
                .time(time=datetime.fromtimestamp(int(mqtt_data["TimeStamp"]) / 1000, UTC),
                    write_precision='ms')
            )

            with influx_client.write_api(write_options=write_options) as write_api:
                write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

        except Exception as e:
            logger.error("Send data to InfluxDB failed. Error code/reason: %s", e)


if __name__ == "__main__":

    # Configuring connection with InfluxDB database
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
