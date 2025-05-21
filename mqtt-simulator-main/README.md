# Mqtt Simulator

## Features
Thies script simulates PLC device and
it publishes json payload over MQTT 
for different kind of sensors and messages.

## How to use

Create virt env for the project:
```sh
python -m venv myvenv
```
<br>

If needed install venv for proper Python version:
```
sudo apt install python3.12-venv
```
<br>

Activate virtual environment:

(Windows):
```
source myvenv/Scripts/activate
```

(Linux):
```
source venv/bin/activate
```
<br>

Install packages into the virt env:
```
(venv) python -m pip install <package-name>
```
or install `requirements.txt`:
```
pip install -r requirements.txt
```