## Multiple signal monitor

This script reads data over MQTT from mutliple sensors(sensor value is FLOAT)

It subscribes to mqtt topic of this schema:
`<LINE_NAME>/<MACHINE_NAME>/#`

and on wildcard `#` level, `<SENSOR_NAME>` of respective sensor is expected. 

The script stores sensor's value and timestamp into InfluxDB.

It expects following JSON in Mqtt payload:
* "LineName": `(string)`
* "MachineName": `(string)`
* "SensorName": `(string)`
* "SensorValue": `(float)`
* "TimeStamp": `(int) - as Epoch Unix (13 digits)`


Examples of air sensor data are depicted on the below screens: 
![signals in grafana](doc/multiple_signal_ex1.png)