'''
Created on 23.11.2017
updated on 19.01.2020 

@author: Florian Gleixner
@Updater: Inonoob

@license: pylarexx is licensed under the Apache License, version 2, see License.txt

DataListener Objects can be added to a Logger instance by configuration of "output".
DataListener get all values from the Sensor instances through the Logger. The can write them to stdout, to file,
serve them on a tcp socket, put them in a database (not implemented) ....
'''

import time
import logging
import socketserver
import threading
import paho.mqtt.client as mqtt
import json
import sqlite3
from influxdb import InfluxDBClient
from datetime import datetime

class DataListener(object):
    def __init__(self, params):
        self.params = params

    def onNewData(self, data):
        raise NotImplementedError


class LoggingListener(DataListener):
    '''
    Listener that uses logging to print data. For debugging purposes
    '''

    def onNewData(self, data):
        logging.info("Datapoint: sensorid %s, raw data: %d cooked: %f %s timestamp: %d from sensor %s type %s" % (
        data['sensor'].displayid, data['rawvalue'], data['sensor'].rawToCooked(data['rawvalue']), data['sensor'].unit,
        data['timestamp'], data['sensor'].name, data['sensor'].type))

class InfluxDBListener(DataListener):
    def __init__(self, params):
        super().__init__(params)
        self.host = self.params.get('host','127.0.0.1')
        self.port = self.params.get('port','8086')
        self.user = self.params.get('user','pi')
        self.password = self.params.get('password','raspberry')
        self.dbname = self.params.get('database')

    def onNewData(self, data):
        client = InfluxDBClient(self.host, self.port, self.user, self.password, self.dbname)
        client.switch_database('arexx')
        current_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        json_body = [
            {
                "measurement": "arexx",
                "tags": {
                    "Location": data['sensor'].name,
                    "sensorid": data['sensor'].displayid,
                    "SensorType": data['sensor'].type,
                    "Unit": data['sensor'].unit
                },
                "time": current_time,
                "fields": {
                    "SensorValue": data['sensor'].rawToCooked(data['rawvalue'])
                }
            }
        ]

        client.write_points(json_body)


class Sqlite3Listener(DataListener):
    '''
    Listener that outputs into an sqlite database
    '''
    def __init__(self, params):
        super().__init__(params)
        self.filename = self.params.get('filename', '/tmp/pylarexx.db')

    def onNewData(self, data):
        conn = sqlite3.connect(self.filename)
        curs = conn.cursor()

        sqlTable = '''CREATE TABLE IF NOT EXISTS pylarexx (id INTEGER PRIMARY KEY, timestamp long, Location string, sensorid integer, SensorType string, SensorValue float, Unit string);'''
        sqlValues ='''INSERT INTO pylarexx (timestamp, Location, sensorid, SensorType, SensorValue, Unit) VALUES (?,?,?,?,?,?);'''

        data_tuple = (data['timestamp'], data['sensor'].name, data['sensor'].displayid,data['sensor'].type,data['sensor'].rawToCooked(data['rawvalue']),data['sensor'].unit)

        curs.execute(sqlTable)
        curs.execute(sqlValues,data_tuple)
        conn.commit()
        conn.close()


class FileOutListener(DataListener):
    '''
    Listener that saves Data to a file
    '''

    def __init__(self, params):
        super().__init__(params)
        self.filename = self.params.get('filename', '/tmp/pylarexx.out')
        self.status = 'not initialized'
        self.openLogfile()

    def openLogfile(self):
        try:
            # TODO: close file
            self.fd = open(self.filename, 'a')
            self.status = 'ready'
        except Exception as e:
            self.status = 'error'
            logging.error("FileOutListener: Unable to open file %s. Error message: %s" % (self.filename, e))

    def onNewData(self, data):
        if self.status != 'ready':
            self.openLogfile()

        if self.status == 'ready':
            if data['signal'] == None:
                signaltext = "-"
            else:
                signaltext = str(data['signal'])
            self.fd.write('%d,%d,%f %s,%d,%s,%s,%s\n' % (
            data['sensor'].displayid, data['rawvalue'], data['sensor'].rawToCooked(data['rawvalue']), data['sensor'].unit,
            data['timestamp'], signaltext, data['sensor'].name, data['sensor'].type))


class RecentValuesListener(DataListener):
    '''
    Listener holds last value from each sensor. Listener can be queried over tcp
    '''

    def __init__(self, params):
        super().__init__(params)
        self.values = {}
        self.ready = False
        self.openListeningPort()

    def openListeningPort(self):
        # make values visible in helper class
        values = self.values

        # helper classes
        class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):

            def setup(self):
                response = ''
                for sid, data in values.items():
                    if data['signal'] == None:
                        signaltext = "-"
                    else:
                        signaltext = str(data['signal'])
                    response += '%d,%f %s,%d,%s,%s,%s\n' % (
                    sid, data['sensor'].rawToCooked(data['rawvalue']), data['sensor'].unit, data['timestamp'],
                    signaltext, data['sensor'].type, data['sensor'].name)

                self.request.sendall(bytes(response, 'UTF-8'))

        class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            pass

        # start tcp server
        try:
            host = self.params.get('host', 'localhost')
            port = self.params.get('port', 4711)
            logging.info("Creating TCP server at %s:%s" % (host, port))
            server = ThreadedTCPServer((host, int(port)), ThreadedTCPRequestHandler)
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            logging.debug("Starting TCP server")
            server_thread.start()
            self.ready = True
        except Exception as e:
            logging.error("Unable to start TCP Server: %s", e)

    def onNewData(self, data):
        self.values[data['sensor'].displayid] = data
        if not self.ready:
            self.openListeningPort()


class MQTTListener(DataListener):
    '''
    Listener that sends values to a MQTT Broker
    Data are formatted following the mqtt homie convention:
    https://homieiot.github.io/
    https://homieiot.github.io/specification/

    and/or the home assistant mqtt auto discovery format

    https://www.home-assistant.io/docs/mqtt/discovery/

    '''

    def __init__(self, params):
        super().__init__(params)
        self.mqttClient = mqtt.Client()
        self.values = {}
        self.ready = False
        self.connect()

    def on_connect(self, client, userdata, flags, rc):
        logging.info("Connected to mqtt broker with result code %d", rc)
        # Subscribe to anything? Not at the moment.

    def on_message(self, client, userdata, msg):
        logging.debug("Got message from mqtt broker: %s / %s", (msg.topic, msg.payload))

    def connect(self):

        try:
            host = self.params.get('host', 'localhost')
            port = self.params.get('port', 1883)
            logging.info("Connecting to mqtt broker at %s:%s" % (host, port))
            self.mqttClient.on_connect = self.on_connect;
            self.mqttClient.on_message = self.on_message;

            self.mqttClient.connect(host, port)
            self.mqttClient.loop_start()
            self.ready = True
        except Exception as e:
            logging.error("Unable to communicate with mqtt broker: %s", e)

    def onNewData(self, data):
        payloadFormat = self.params.get('payload_format', 'home-assistant')
        if payloadFormat == 'homie':
            self.sendHomieMessages(data)
        if payloadFormat == 'home-assistant':
            self.sendHomeAssistantMessage(data)

    def sendHomeAssistantMessage(self, data):
        try:
            newSensor = False
            self.values[data['sensor'].displayid]
        except Exception as e:
            newSensor = True
        if self.ready:
            try:
                topicroot = '%s/%s' % (self.params.get('mqtt_base_topic', 'homeassistant'), 'sensor')
                topicconfig = '%s/%s_%s/config' % (
                topicroot, self.params.get('mqtt_device', 'pylarexx'), data['sensor'].displayid)
                topicstate = '%s/%s_%s/state' % (
                topicroot, self.params.get('mqtt_device', 'pylarexx'), data['sensor'].displayid)

                if newSensor:
                    logging.debug('New Sensor config')
                    unit_of_measurement = data['sensor'].unit
                    if unit_of_measurement == '%RH':
                        unit_of_measurement = '%'

                    payload = {'name': '%s %s' % (data['sensor'].name, data['sensor'].type),
                               'device_class': data['sensor'].type.lower(),
                               'state_topic': topicstate,
                               'unit_of_measurement': unit_of_measurement,
                               'value_template': '{{value_json.%s}}' % data['sensor'].type.lower(),
                               }
                    self.mqttClient.publish(topicconfig, json.dumps(payload), 0, True)
                statePayload = {}
                statePayload[data['sensor'].type.lower()] = '%.2f' % data['sensor'].rawToCooked(data['rawvalue'])
                self.mqttClient.publish(topicstate, json.dumps(statePayload))

            except Exception as e:
                logging.error("Error publishing mqtt messages: %s", e)

    def sendHomieMessages(self, data):
        try:
            newSensor = False
            self.values[data['sensor'].displayid]
        except Exception as e:
            newSensor = True
        self.values[data['sensor'].displayid] = data
        if self.ready:
            try:
                topicroot = '%s/%s' % (
                self.params.get('mqtt_base_topic', 'homie'), self.params.get('mqtt_device', 'pylarexx'))

                logging.debug("publishing MQTT messages with topic root %s" % topicroot)
                if newSensor:
                    logging.debug("Updating MQTT device")
                    self.mqttClient.publish('%s/$homie' % topicroot, self.params.get('homie_convention_version', '3.0'),
                                            0, True)
                    self.mqttClient.publish('%s/$name' % topicroot, self.params.get('mqtt_device_name',
                                                                                    'Python MQTT Adapter for Arexx Multilogger'),
                                            0, True)
                    nodes = []
                    for sid, value in self.values.items():
                        nodes.append('sensor_%d' % sid)
                    nodestring = ','.join(nodes)
                    self.mqttClient.publish('%s/$nodes' % topicroot, nodestring, 0, True)  # does this work?
                    self.mqttClient.publish('%s/$state' % topicroot, "ready", 0, True)

                    for sid, value in self.values.items():
                        logging.debug("Sending MQTT sensor values")
                        self.mqttClient.publish('%s/sensor_%d/$type' % (topicroot, sid),
                                                value['sensor'].manufacturerType)
                        self.mqttClient.publish('%s/sensor_%d/$name' % (topicroot, sid), value['sensor'].name)
                        self.mqttClient.publish('%s/sensor_%d/$properties' % (topicroot, sid),
                                                value['sensor'].type.lower())
                        self.mqttClient.publish(
                            '%s/sensor_%d/%s/$name' % (topicroot, sid, value['sensor'].type.lower()),
                            '%s %s' % (value['sensor'].name, value['sensor'].type))
                        self.mqttClient.publish(
                            '%s/sensor_%d/%s/$datatype' % (topicroot, sid, value['sensor'].type.lower()), 'float')
                        self.mqttClient.publish(
                            '%s/sensor_%d/%s/$unit' % (topicroot, sid, value['sensor'].type.lower()),
                            value['sensor'].unit)
                        self.mqttClient.publish('%s/sensor_%d/%s' % (topicroot, sid, value['sensor'].type.lower()),
                                                '%.2f' % value['sensor'].rawToCooked(value['rawvalue']))
                else:
                    logging.debug("Sending MQTT sensor values")
                    sid = data['sensor'].displayid
                    self.mqttClient.publish('%s/sensor_%d/$type' % (topicroot, sid), data['sensor'].manufacturerType)
                    self.mqttClient.publish('%s/sensor_%d/$name' % (topicroot, sid), data['sensor'].name)
                    self.mqttClient.publish('%s/sensor_%d/$properties' % (topicroot, sid), data['sensor'].type.lower())
                    self.mqttClient.publish('%s/sensor_%d/%s/$name' % (topicroot, sid, data['sensor'].type.lower()),
                                            '%s %s' % (data['sensor'].name, data['sensor'].type))
                    self.mqttClient.publish('%s/sensor_%d/%s/$datatype' % (topicroot, sid, data['sensor'].type.lower()),
                                            'float')
                    self.mqttClient.publish('%s/sensor_%d/%s/$unit' % (topicroot, sid, data['sensor'].type.lower()),
                                            data['sensor'].unit)
                    self.mqttClient.publish('%s/sensor_%d/%s' % (topicroot, sid, data['sensor'].type.lower()),
                                            '%.2f' % data['sensor'].rawToCooked(data['rawvalue']))
            except Exception as e:
                logging.error("Error publishing mqtt messages: %s", e)




