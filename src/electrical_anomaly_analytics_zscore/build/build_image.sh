#!bin/bash

sudo docker build --build-arg date=$(date -u +'%Y-%m-%dT%H:%M:%SZ') --tag electrical_analytics_z_score_mqtt_img:0.0.1 ../. 
