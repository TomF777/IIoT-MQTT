#!bin/bash

sudo docker build --build-arg date=$(date -u +'%Y-%m-%dT%H:%M:%SZ') --tag single_signal_anomaly_detect_zscore_mqtt_img:0.0.1 ../. 
