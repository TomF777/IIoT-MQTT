"""
    The script catches data over mqtt from one electrical device.
    It calculates analytics like definite integral over fixed time,
    electrical current assymetry and inrush current.
    Anomaly detection algorithm is then applied to 
    integral value and inrush current.
    Analytics results and timestamp are saved in InfluxDB.
    It also stores raw electrical data to InfluxDB.

    The script subscribes to 
    'MachineName/LineName/DeviceName' topic level.
"""
import json
import logging
from datetime import datetime, UTC
import paho.mqtt.client as mqtt
import influxdb_client
from influxdb_client.client.write_api import WriteOptions
from scipy.signal import find_peaks
from helper import AnomalyDetectionZscore, ElectricalAnalytics, get_env_var

# Set up logging configuration
LOG_FORMAT = "%(levelname)s %(asctime)s \
    Function: %(funcName)s \
    Line: %(lineno)d \
    Message: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


# Assignment const variable from env or created using env
logger.info("Setting const global variables")

LINE_NAME = get_env_var("LINE_NAME", str)
MACHINE_NAME = get_env_var("MACHINE_NAME", str)
DEVICE_NAME = get_env_var("DEVICE_NAME", str)

MQTT_USERNAME = get_env_var("MQTT_USERNAME", str)
MQTT_PASSWORD = get_env_var("MQTT_PASSWORD", str)
MQTT_HOST = get_env_var("MQTT_HOST", str)
MQTT_PORT = get_env_var("MQTT_PORT", int)
MQTT_QOS = get_env_var("MQTT_QOS", int)
MQTT_TOPIC = LINE_NAME + "/" + MACHINE_NAME + "/" + DEVICE_NAME
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
logger.info("INFLUX_URL value is: %s", INFLUX_URL)

# which current peak in a row should be taken into inrush current detection
CURRENT_PEAK_NUMBER = get_env_var("CURRENT_PEAK_NUMBER", int, default=1)

# electrical current threshold for peak detection algorithm
CURRENT_PEAK_HEIGHT = get_env_var("CURRENT_PEAK_HEIGHT", float, default=1.0)

#Threshold for z-score value. Point above this threshold is treated as anomaly
Z_SCORE_THRESHOLD = get_env_var("Z_SCORE_THRESHOLD", float, default=2.0)

# number of model points in a list to calculate anomaly
MODEL_WINDOW_SIZE = get_env_var("MODEL_WINDOW_SIZE", int, default=25)

# number of anomaly points in a list to calculate anomaly ratio
ANOMALY_LIST_SIZE = get_env_var("ANOMALY_LIST_SIZE", int, default=25)

electrical_analytics = ElectricalAnalytics()

el_current_integr_ph1_analytics = AnomalyDetectionZscore("el_current_integr_ph1_analytics",
                                                    MODEL_WINDOW_SIZE,
                                                    ANOMALY_LIST_SIZE,
                                                    logger)

el_current_integr_ph2_analytics = AnomalyDetectionZscore("el_current_integr_ph2_analytics",
                                                    MODEL_WINDOW_SIZE,
                                                    ANOMALY_LIST_SIZE,
                                                    logger)

el_current_integr_ph3_analytics = AnomalyDetectionZscore("el_current_integr_ph3_analytics",
                                                    MODEL_WINDOW_SIZE,
                                                    ANOMALY_LIST_SIZE,
                                                    logger)

el_inrush_current_ph1_analytics = AnomalyDetectionZscore("el_inrush_current_ph1_analytics",
                                                    MODEL_WINDOW_SIZE,
                                                    ANOMALY_LIST_SIZE,
                                                    logger)

el_inrush_current_ph2_analytics = AnomalyDetectionZscore("el_inrush_current_ph2_analytics",
                                                    MODEL_WINDOW_SIZE,
                                                    ANOMALY_LIST_SIZE,
                                                    logger)

el_inrush_current_ph3_analytics = AnomalyDetectionZscore("el_inrush_current_ph3_analytics",
                                                    MODEL_WINDOW_SIZE,
                                                    ANOMALY_LIST_SIZE,
                                                    logger)


def calculate_integr_analytics(el_current_ph1_samples,
                                el_current_ph2_samples,
                                el_current_ph3_samples,
                                z_threshold_integr
                                ):
    """Calculate definite integral of electrical current samples """

    el_current_integr_ph1_total = el_current_ph1_samples.sum()
    el_current_integr_ph2_total = el_current_ph2_samples.sum()
    el_current_integr_ph3_total = el_current_ph3_samples.sum()

    el_current_integr_ph1_analytics.z_score_thresh = z_threshold_integr
    el_current_integr_ph2_analytics.z_score_thresh = z_threshold_integr
    el_current_integr_ph3_analytics.z_score_thresh = z_threshold_integr

    el_current_integr_ph1_analytics.check_if_anomaly(el_current_integr_ph1_total)
    el_current_integr_ph2_analytics.check_if_anomaly(el_current_integr_ph2_total)
    el_current_integr_ph3_analytics.check_if_anomaly(el_current_integr_ph3_total)

    el_current_integr_ph1_analytics.calculate_anomaly_ratio()
    el_current_integr_ph2_analytics.calculate_anomaly_ratio()
    el_current_integr_ph3_analytics.calculate_anomaly_ratio()
    return el_current_integr_ph1_total, \
            el_current_integr_ph2_total, \
            el_current_integr_ph3_total


def calculate_el_current_assymetry(el_current_integr_ph1_total,
                                   el_current_integr_ph2_total,
                                   el_current_integr_ph3_total):
    """
    Calculate electrical current assymetry

    Args:
        el_current_integr_ph1/2/3_total: total finite integral value from collected samples 
    """

    el_current_integr_mean = (el_current_integr_ph1_total +
                    el_current_integr_ph2_total +
                    el_current_integr_ph3_total) / 3

    el_current_assymetry = 100 * ((
                            abs(el_current_integr_ph1_total - el_current_integr_mean) + \
                            abs(el_current_integr_ph2_total - el_current_integr_mean) + \
                            abs(el_current_integr_ph3_total - el_current_integr_mean)
    ) / el_current_integr_mean)

    return el_current_assymetry


def calculate_inrush_current_analytics(el_current_ph1_samples,
                                       el_current_ph2_samples,
                                       el_current_ph3_samples,
                                       z_threshold_inrush,
                                       height_of_peak,
                                       peak_number):
    """
    Calculate inrush current in electrical current samples

    Args:
        el_current_ph1/2/3_samples: electrical current samples from phase L1/L2/L3
        height_of_peak: threshold for peak detection algorithm 
        peak_number: which peak in a row should be taken into inrush current detection
    """

    # Find inrush current as first peak in electrical current curve
    el_current_peaks_ph1, _ = find_peaks(el_current_ph1_samples, height=height_of_peak)
    el_current_peaks_ph2, _ = find_peaks(el_current_ph2_samples, height=height_of_peak)
    el_current_peaks_ph3, _ = find_peaks(el_current_ph3_samples, height=height_of_peak)

    # Check if inrush current L1,L2,L3 is anomaly (first founded peak = inrush current)
    if len(el_current_peaks_ph1) > 0 and peak_number <= len(el_current_peaks_ph1):
        inrush_current_ph1 = el_current_ph1_samples[el_current_peaks_ph1[peak_number-1]]
        el_inrush_current_ph1_analytics.z_score_thresh = z_threshold_inrush
        el_inrush_current_ph1_analytics.check_if_anomaly(inrush_current_ph1)
        el_inrush_current_ph1_analytics.calculate_anomaly_ratio()

    if len(el_current_peaks_ph2) > 0 and peak_number <= len(el_current_peaks_ph2):
        inrush_current_ph2 = el_current_ph2_samples[el_current_peaks_ph2[peak_number-1]]
        el_inrush_current_ph2_analytics.z_score_thresh = z_threshold_inrush
        el_inrush_current_ph2_analytics.check_if_anomaly(inrush_current_ph2)
        el_inrush_current_ph2_analytics.calculate_anomaly_ratio()

    if len(el_current_peaks_ph3) > 0 and peak_number <= len(el_current_peaks_ph3):
        inrush_current_ph3 = el_current_ph3_samples[el_current_peaks_ph3[peak_number-1]]
        el_inrush_current_ph3_analytics.z_score_thresh = z_threshold_inrush
        el_inrush_current_ph3_analytics.check_if_anomaly(inrush_current_ph3)
        el_inrush_current_ph3_analytics.calculate_anomaly_ratio()

    try:
        return inrush_current_ph1, \
                inrush_current_ph2, \
                inrush_current_ph3
    except Exception as e:
        logger.error(" Error: %s - No inrush current detected ", e)
        return False, False, False




def on_connect(mqttclient, userdata, flags, rc, properties):
    """Method triggered by mqtt on connect callback and log information about status of connection

    Args:
        mqttclient:         the client instance for this callback
        userdata:           the private user data as set in Client() or userdata_set()
        flags:              response flags sent by the broker
        rc:                 the connection result code
        properties:         properties
    """

    if rc == 0:
        logger.info("Connection to MQTT Broker successful. Result Code: 0")
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


def on_disconnect(mqttclient, userdata,flags, rc, properties):
    """Method triggered by mqtt on disconnect callback and log information about lost connection

    Args:
        mqttclient: the client instance for this callback
        userdata:  the private user data as set in Client() or userdata_set()
        rc: the connection result code
        properties: properties
    """
    logger.info("Lost conection with MQTT Broker. Result Code: %s", rc)



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
        device_name = mqtt_data["DeviceName"]
        device_state = mqtt_data["DeviceState"]
        synch_pulse = mqtt_data["SynchPulse"]
        el_current_phase1 = mqtt_data["ElectricalData"]["CurrentL1"]
        el_current_phase2 = mqtt_data["ElectricalData"]["CurrentL2"]
        el_current_phase3 = mqtt_data["ElectricalData"]["CurrentL3"]
    except Exception as e:
        logger.error("No valid device data in json included")

    else:

        if device_state == "Running":
            # save data to array while device in 'Running' state
            electrical_analytics.append_samples(el_current_phase1,
                                                el_current_phase2,
                                                el_current_phase3)

        elif device_state != "Running" and synch_pulse is True:
        # Reinitilize(clear) array with samples when not 'Running' and SynchPulse true
        # Running state must be longer than SynchPulse
            electrical_analytics.clear_samples()
        elif (
            # not 'Running' anymore and enough samples collected
            device_state != "Running"
            and electrical_analytics.samples_number_ph1 > 0
            and electrical_analytics.samples_number_ph2 > 0
            and electrical_analytics.samples_number_ph3 > 0):

            # Calculate definite integral of electrical current samples
            # and check if it is anomaly
            electrical_analytics.el_current_integr_ph1_total,\
            electrical_analytics.el_current_integr_ph2_total,\
            electrical_analytics.el_current_integr_ph3_total = \
            calculate_integr_analytics(electrical_analytics.el_current_ph1_samples,
                                        electrical_analytics.el_current_ph2_samples,
                                        electrical_analytics.el_current_ph3_samples,
                                        Z_SCORE_THRESHOLD
                        )

            # Calculate electrical current assymetry
            el_current_assymetry = calculate_el_current_assymetry(
                                                electrical_analytics.el_current_integr_ph1_total,
                                                electrical_analytics.el_current_integr_ph2_total,
                                                electrical_analytics.el_current_integr_ph3_total,
                                        )

            # Calculate inrush current and check if it is anomaly
            el_inrush_current_ph1, \
            el_inrush_current_ph2, \
            el_inrush_current_ph3, = \
            calculate_inrush_current_analytics(
                                        electrical_analytics.el_current_ph1_samples,
                                        electrical_analytics.el_current_ph2_samples,
                                        electrical_analytics.el_current_ph3_samples,
                                        Z_SCORE_THRESHOLD,
                                        CURRENT_PEAK_HEIGHT,
                                        CURRENT_PEAK_NUMBER)

            # Store analytics results in InfluxDB
            try:
                measurement = ("ElectricalAnalytics")
                point = (
                    influxdb_client.Point(measurement)
                    .tag("line_name", str(mqtt_data["LineName"]))
                    .tag("machine_name", str(mqtt_data["MachineName"]))
                    .tag("device_name", device_name)
                    .field("el_current_assymetry", round(float(el_current_assymetry), 2))
                    .field("el_current_integral_ph1", round(float(electrical_analytics.el_current_integr_ph1_total), 4))
                    .field("el_current_integral_ph2", round(float(electrical_analytics.el_current_integr_ph2_total), 4))
                    .field("el_current_integral_ph3", round(float(electrical_analytics.el_current_integr_ph3_total), 4))
                    .field("el_current_integral_ph1_z_score", round(float(el_current_integr_ph1_analytics.z_score), 4))
                    .field("el_current_integral_ph1_z_score_thresh", round(float(el_current_integr_ph1_analytics.z_score_thresh), 4))
                    .field("el_current_integral_ph2_z_score", round(float(el_current_integr_ph2_analytics.z_score), 4))
                    .field("el_current_integral_ph2_z_score_thresh", round(float(el_current_integr_ph2_analytics.z_score_thresh), 4))
                    .field("el_current_integral_ph3_z_score", round(float(el_current_integr_ph3_analytics.z_score), 4))
                    .field("el_current_integral_ph3_z_score_thresh", round(float(el_current_integr_ph3_analytics.z_score_thresh), 4))
                    
                    .field("el_current_integral_ph1_anomaly", int(el_current_integr_ph1_analytics.anomaly))
                    .field("el_current_integral_ph2_anomaly", int(el_current_integr_ph2_analytics.anomaly))
                    .field("el_current_integral_ph3_anomaly", int(el_current_integr_ph3_analytics.anomaly))
                    .field("el_current_integral_ph1_anomaly_ratio", round(float(el_current_integr_ph1_analytics.anomaly_ratio), 4))
                    .field("el_current_integral_ph2_anomaly_ratio", round(float(el_current_integr_ph2_analytics.anomaly_ratio), 4))
                    .field("el_current_integral_ph3_anomaly_ratio", round(float(el_current_integr_ph3_analytics.anomaly_ratio), 4))
                    .field("el_inrush_current_ph1", round(float(el_inrush_current_ph1), 4))
                    .field("el_inrush_current_ph2", round(float(el_inrush_current_ph2), 4))
                    .field("el_inrush_current_ph3", round(float(el_inrush_current_ph3), 4))
                    .field("el_inrush_current_ph1_anomaly", int(el_inrush_current_ph1_analytics.anomaly))
                    .field("el_inrush_current_ph2_anomaly", int(el_inrush_current_ph2_analytics.anomaly))
                    .field("el_inrush_current_ph3_anomaly", int(el_inrush_current_ph3_analytics.anomaly))
                    .field("el_inrush_current_ph1_anomaly_ratio", round(float(el_inrush_current_ph1_analytics.anomaly_ratio), 4))
                    .field("el_inrush_current_ph2_anomaly_ratio", round(float(el_inrush_current_ph2_analytics.anomaly_ratio), 4))
                    .field("el_inrush_current_ph3_anomaly_ratio", round(float(el_inrush_current_ph3_analytics.anomaly_ratio), 4))
                    .time(time=datetime.fromtimestamp(int(mqtt_data["TimeStamp"]) / 1000, UTC),
                        write_precision='ms')
                )

                with influx_client.write_api(write_options=write_options) as write_api:
                    write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

            except Exception as e:
                logger.error("Send data to InfluxDB failed. Error code/reason: %s", e)

            # Clear samples after data sent to InfluxDB
            electrical_analytics.clear_samples()


# Main function of script
if __name__ == "__main__":

    # Configure connection to InfluxDB database
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

    # Set up MQTT connection and subscribe to topic
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
