import os
import statistics
import logging
import numpy as np

helper_logger = logging.getLogger(__name__)

def get_params(
    env: str, req_type=None, default: str | int | float = None
) -> str | int | float:
    """Read env variables and return its value with log information

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
        helper_logger.error(
            f"Cannot convert value of env {env} to {req_type}. \
                Allowed conversion type: str, int, float"
        )
        raise SystemExit

    # Return value of env variable
    if env_val is None and default is None:
        # env does not exist and we did not set default value
        helper_logger.error(f"Env variable {env} does not exist")
        raise SystemExit
    elif env_val is None:
        # env does not exist but return default (default is different than none)
        helper_logger.warning(
            f"Env variable {env} does not exist, return default value: {default}"
        )
        return default
    elif env_type is not req_type and req_type is not None:
        # env var exist and it's type is diffrent than what we set
        try:
            converted_env = req_type(env_val)
            helper_logger.info(
                f"Env variable {env} value: {env_val}. Converted from {env_type} to {req_type}."
            )
            return converted_env
        except Exception as e:
            helper_logger.error(
                f"Convert env variable {env} from {env_type} to {req_type} failed: {e}"
            )
            raise SystemExit
    else:
        # env exist, is the same type (or we not set type) so we return it
        helper_logger.info(f"Env variable {env} value: {env_val}, type: {env_type}")
        return env_val


class ElectricalAnalytics:
    """ Class to store electrical current samples and calculate definite integral"""

    def __init__(self ) -> None:
        # array where electrical current samples are stored
        self.el_current_ph1_samples = np.array([])
        self.el_current_ph2_samples = np.array([])
        self.el_current_ph3_samples = np.array([])

        # calculated definite integral of electrical current samples
        self.el_current_integr_ph1_total = 0
        self.el_current_integr_ph2_total = 0
        self.el_current_integr_ph3_total = 0

    def append_samples(self, phase1, phase2, phase3):
        """Append new samples to array of electrical current samples"""
        self.el_current_ph1_samples = np.append(self.el_current_ph1_samples, phase1)
        self.el_current_ph2_samples = np.append(self.el_current_ph2_samples, phase2)
        self.el_current_ph3_samples = np.append(self.el_current_ph3_samples, phase3)

    def clear_samples(self):
        """Clear array of electrical current samples"""
        self.el_current_ph1_samples = np.array([])
        self.el_current_ph2_samples = np.array([])
        self.el_current_ph3_samples = np.array([])

    @property
    def samples_number_ph1(self) -> int:
        """Return number of samples in array"""
        return len(self.el_current_ph1_samples)

    @property
    def samples_number_ph2(self) -> int:
        """Return number of samples in array"""
        return len(self.el_current_ph2_samples)

    @property
    def samples_number_ph3(self) -> int:
        """Return number of samples in array"""
        return len(self.el_current_ph3_samples)


class AnomalyDetection3StdDev:
    """
        Analyse real-time data from sensor
        and apply +-3 std dev algorithm to detect anomalies

        model_data              list where real-time (non anomalous) data are stored
        model_size              definition how many data points should be in `model_data`
        anomaly_list            list with anomaly detection results (1 and 0)
        anomaly_list_size       definition how many anomaly points should be in `anomaly_list`
        anomaly_ratio           percentage of anomalous data in `anomaly_list`
        anomaly                 result if current data point is anomaly (1) or not (0)
        model_avg               avarage mean of `model_data`
        model_std_dev           standard deviation of `model_data`
        thresh_std_dev_limit    used to calculate up_threshold and lo_threshold
                                    when std dev is below set limit
        u_thresh                calculated positive limit above which data is treated as anomaly
        l_thresh                calculated negative limit below which data is treated as anomaly
        name                    name of the object/sensor on which the algorithm is applied

    """

    # Init function
    def __init__(self, name: str,
                 model_size: int,
                 anomaly_list_size: int,
                 thresh_std_dev_limit: float) -> None:
        self._model_data = []
        self._model_size = model_size
        self._anomaly_list = []
        self._anomaly_list_size = anomaly_list_size
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._thresh_std_dev_limit = thresh_std_dev_limit
        self._u_thresh = 0.0
        self._l_thresh = 0.0
        self._name = name

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
        return True

    def is_model_complete(self) -> bool:
        """Return True if data model has enough data points"""
        return True if len(self._model_data) == self._model_size else False


    def calculate_anomaly_ratio(self):
        """Sum all anomalies results (0 and 1) from `anomaly_list`
           and divide it by the size of the list

        """
        try:
            if not self.is_model_complete():
                pass
            elif len(self._anomaly_list) < self._anomaly_list_size:
                self._anomaly_list.append(self._anomaly)
            else:
                self._anomaly_list.pop(0)
                self._anomaly_list.append(self._anomaly)
                self._anomaly_ratio = round(sum(self._anomaly_list) / self._anomaly_list_size, 3)
        except Exception as e:
            helper_logger.error(
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
                    self._u_thresh = self._model_avg + self._thresh_std_dev_limit
                    self._l_thresh = self._model_avg - self._thresh_std_dev_limit
                else:
                    # Use +- 3 std dev method to calculate low and high limit
                    self._u_thresh = self._model_avg + 3 * self._model_std_dev
                    self._l_thresh = self._model_avg - 3 * self._model_std_dev

                # Check if new point is anomaly (is out of limit)
                if self._l_thresh <= value <= self._u_thresh:
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
            helper_logger.error(
                f'Calculation anomaly of model "{self._name}" failed. Error code/reason: {e}'
            )


class AnomalyDetectionZscore:
    pass