#!bin/bash

sudo docker build --build-arg date=$(date -u +'%Y-%m-%dT%H:%M:%SZ') --tag air_valve_zscore_img:0.0.1 ../. 
