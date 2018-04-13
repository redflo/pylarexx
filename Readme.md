# Pylarexx - Python DataLogger for Arexx Multilogger Devices

Pylarexx searches the USB bus for [Arexx](http://www.arexx.com/templogger/html/en/index.php) BS-500 / TL-500 devices, and constantly reads sensor data. It can be configured to name the sensors, add calibration values and configure output modules.

At the moment the BS-510 / TL-510 devices are not supported, since i have no such device. New Arexx sensors have id values that exceed 2 bytes and need this newer device. Would be nice, if someone sends me a device or a patch.

The sensors that i have tested are TSN-TH70E and TL-3TSN, both with 2-byte id numbers (<65536). If you have other sensors (CO2, ...), you can send me sensors or debugging output, and i will try to add them.


  
## Installation

Pylarexx is tested with Linux. Installing and running pylarexx requires root privileges. 
The install.sh should put the code to /usr/local/pylarexx, a example config to /etc/pylarexx.yml and on systemd based systems, it creates a service.

## Configuration

All configuration is done in /etc/pylarexx.yml. Be careful about indentation and "-", since this has a special meaning in yaml files. See [YAML Wikipedia Article](https://en.wikipedia.org/wiki/YAML).

### Sensors
At *sensors* you should add your sensors as shown in the example config.

### Calibration
At *calibration* you can add calibration values. Usually the values for temperature, humidity, ... are computed from the raw value from the sensor with:

`value = p0 + rawvalue * p1 + rawvalue² * p2 + ....`

With the values List, you can alter p0, p1 .... as shown in the example config.

### Output

At *output* you can add one or more DataListeners and configure them. You can also add one type of DataListener more then one time.

#### Available output modules (DataListeners):

- LoggingListener: Uses python logging to print measured values
- FileOutListener: Appends measured values to a file
    * Parameter: *filename* default value: /tmp/pylarexx.out
- RecentValuesListener: Makes recent values of all sensors available to a TCP socket. This can be queried with "nc". Useful for example, if you want to monitor sensor values with nagios/icinga/check_mk
    * Parameter: *host* IP to listen, default value: localhost
    * Parameter: *port* TCP Port, default value: 4711
    
Planned:
- Log to Grafana
- Log to Elasticsearch/Solr
- Log to mysql/postgres
- Log to influxdb
- Log to a REST API
- ....

Look at DataListener.py to see how to implement new output modules

### Other config

At *config* there are some other configuration options:

* DetectUnknownSensors: Default: yes. If set to "no", pylarexx will only see the configured sensors. Good if you have other types of sensors, that create ghost entries.


## License

pylarexx is licensed under the Apache License, version 2, see License.txt.
The file device.xml is copyrighted by Arexx and is distributed with permission from Arexx
