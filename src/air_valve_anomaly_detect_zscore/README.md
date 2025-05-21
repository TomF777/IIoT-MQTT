## Air valve travel time anomaly detection with z-score algorithm 

Script reads air valve travel times over MQTT,
calculates anomaly using z-score method and stores results to InfluxDB

The script subscribes to mqtt topic of this schema:
`<LINE_NAME>/<MACHINE_NAME>/<SENSOR_NAME>`

It expects following JSON in Mqtt payload:

* "LineName": `str`
* "MachineName": `str`
* "ValveName": `str`
* "TimeType": `str e.g. Extend/Retract`
* "TimeValue": `int - in miliseconds`
* "TimeStamp": `int - as Epoch Unix (13 digits)`
