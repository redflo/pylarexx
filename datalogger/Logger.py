'''
Created on 23.11.2017

@author: Florian Gleixner
@license: pylarexx is licensed under the Apache License, version 2, see License.txt

'''

import usb.core
import time
import math
import array
import datalogger.Sensor
import datalogger.DataListener
from datalogger.DataListener import DataListener
import logging
import yaml
from datalogger.Sensor import ArexxSensorDetector
from datetime import datetime
from pprint import pformat

# import traceback


class TLX00(object):
    '''
    This class handles USB connection and communication for Arexx TL-300 and TL-500 devices and BS-510
    '''
    TIME_OFFSET = 946681200           # Timestamp of 2000-01-01 00:00:00

    def __init__(self, params):
        self.devices=[]
        self.listeners=[]
        self.sensors={}
        self.requestBuffer = array.array('B', [0]*64)
        self.config={}
        self.detectUnknownSensors=True
        self.lastDeviceCheck=0
        if 'conffile' in params:
            self.readConfigFile(params['conffile'])

## This method extract the information stored in the config file /etc/pylarexx.yml with the differnt config sections ##

    def readConfigFile(self,filename):
        with open(filename) as f:
            content=f.read()
            self.config=yaml.load(content)
            logging.debug(self.config)

        if 'sensors' in self.config:
            try:
                for sensor in self.config['sensors']:
                    sensorid=int(sensor['id'])
                    sensortype=None
                    if 'type' in sensor:
                        sensortype=sensor['type']
                    name = None
                    if 'name' in sensor:
                        name=sensor['name']
                    logging.info("Adding Sensor from config file: %d %s %s"%(sensorid,sensortype,name))
                    # Todo: Sensortype weg machen
                    if sensortype in ('TL-3TSN','TSN-50E','TSN-EXT44','TSN-33MN'):
                        self.sensors[sensorid]=datalogger.Sensor.ArexxTemperatureSensor(sensorid,sensortype,name)
                    elif sensortype in ('TSN-TH70E', 'TSN-TH77ext'):
                        self.sensors[sensorid]=datalogger.Sensor.ArexxTemperatureSensor(sensorid,sensortype,name)
                        self.sensors[sensorid+1]=datalogger.Sensor.ArexxHumiditySensor(sensorid+1,sensortype,name)
                    else:
                        # Bug? TSN-TH70E #20444 is not added by this code
                        detected_sensor = self.detectSensor(sensorid, name)
                        if detected_sensor != False:
                            self.addSensor(detected_sensor)
                        else:
                            self.sensors[sensorid]= datalogger.Sensor.Sensor(sensorid)
                            self.sensors[sensorid].setName(name)
            except Exception as e:
                logging.error('Error in config section sensors: %s',e)
                logging.debug('Stacktrace: ',exc_info=True)

        if 'calibration' in self.config:
            for c in self.config['calibration']:
                try:
                    sensorid=int(c['id'])
                    if not sensorid in self.sensors:
                        logging.error('Calibration values found for sensor %i, but sensor not defined in config',sensorid)
                        continue;
                    for n,v in c['values'].items():
                        self.sensors[sensorid].calibrationValues[n] = float(v)
                        logging.debug("Calibration value for sensor %d oder %d value %f"%(sensorid,n,float(v)))
                except Exception as e:
                    logging.error('Error in config section calibration: %s',e)
                    logging.debug('Stacktrace: ',exc_info=True)


        if 'output' in self.config:
            for logger in self.config['output']:
                try:
                    loggerType = logger.get('type')
                    params= logger.get('params',{})
                    listenerClass = getattr(datalogger.DataListener,loggerType)
                    self.registerDataListener(listenerClass(params))
                except Exception as e:
                    logging.error('Error in config section output: %s',e)
                    logging.debug('Stacktrace: ',exc_info=True)

        if 'config' in self.config:
            if 'DetectUnknownSensors' in self.config['config']:
                self.detectUnknownSensors=bool(self.config['config']['DetectUnknownSensors'])

    # detect sensor and return it. Returns False, if no sensor was detected.
    # If detectUnknownSensors is set to false, return a sensor only if it is in config via displayid

    def detectSensor(self,sensorid,name=None):
        detector = ArexxSensorDetector()
        detected_sensor = detector.detectDevice(sensorid)
        is_in_config=False
        if detected_sensor != False:
            logging.debug("Detected Sensor: %s(%s)" % (detected_sensor.id, detected_sensor.type) )
            if name != None:
                detected_sensor.setName(name)
            else:# check if we have a sensor in config with the same display id. Then copy name
                for sensor in self.sensors.items():
                    if sensor[0] == detected_sensor.displayid:
                        detected_sensor.setName(sensor[1].name)
                        logging.info("Setting name of detected sensor to: %s" % detected_sensor.name)
                        is_in_config=True
        if self.detectUnknownSensors or is_in_config:
            return detected_sensor
        return False

    # checks if data match to sensor value range and time
    def validateSensorData(self,data,sensor):
        if abs(time.time() - data["timestamp"]) > 4000: # On DST changes we can get 3600sec difference.
            logging.info("validateSensorData: timestamp %s is stale. Is a buffering receiver used?", datetime.fromtimestamp(data["timestamp"]).strftime('%Y-%m-%d %H:%M:%S'))
        cooked=sensor.rawToCooked(data["rawvalue"])
        if cooked > sensor.valmax or cooked < sensor.valmin:
            logging.info("validateSensorData: Datapoint %f outside range (%f/%f). Ignoring." % (cooked, sensor.valmin, sensor.valmax))
            return False
        return True

    def addSensor(self,detected_sensor):
        logging.info("Adding Sensor %s", detected_sensor.name)
        self.sensors[detected_sensor.id] = detected_sensor

    def removeSensor(self,sensorid):
        logging.info("Removing Sensor %s", self.sensors[sensorid].name)
        self.sensors.pop(sensorid)

# Method to reset the requestBuffer to 0 to have a clean starting buffer
    def clearRequestBuffer(self):
        for i in range(0,63):
            self.requestBuffer[i]=0

# this method looks for logger attached via USB on the system

    def findDevices(self):
        self.lastDeviceCheck = math.floor(time.time())
        founddevices = usb.core.find(find_all= True, idVendor=0x0451, idProduct=0x3211)
        self.devices = list(founddevices)
        if self.devices is not None:
            logging.info("Found Arexx Datalogger device(s) at ")
            for d in self.devices:
                d.lastTimeDataRead = 0
                d.deviceErrors = 0
                d.lastTimeSync = 0
                d.lastTimeDelete = 0
                logging.info("Bus %d Address %d Port Number %d " % (d.bus,d.address,d.port_number))
            return True
        logging.error("No device found")
        return False

    def checkForNewDevices(self):
        self.lastDeviceCheck = math.floor(time.time())
        founddevices = usb.core.find(find_all= True, idVendor=0x0451, idProduct=0x3211)
        numdevices = len(list(founddevices))
        if numdevices != len(self.devices):
            return True
        return False

    def initializeDevices(self):
        for d in self.devices:
            try:
                d.set_configuration()
                cfg = d.get_active_configuration()
                intf = cfg[(0,0)]
                epo = usb.util.find_descriptor(intf, custom_match = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
                epi = usb.util.find_descriptor(intf, custom_match = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN )
                d.outAddress = epo.bEndpointAddress
                d.inAddress = epi.bEndpointAddress
                logging.info("Device on Bus %d Address %d Port Number %d uses Addresses %d/%d for in/out" % (d.bus,d.address,d.port_number,d.inAddress,d.outAddress))
                self.setTime(d)
            except Exception as e:
                logging.error("Error initializing device at Bus %d Address %d Port Number %d. Resetting and removing device" % (d.bus,d.address,d.port_number))
                logging.error("Error Message: %s" % e)
                try:
                    d.reset()
                except Exception as ne:
                    logging.error("Error resetting device: %s" % ne)
                self.devices.remove(d)

# Method to set the time on the logging device

    def setTime(self,device):
        logging.debug("Setting time for USB device at Bus %d Address %d Port Number %d" % (device.bus,device.address,device.port_number))
        # set mode
        self.clearRequestBuffer()
        self.requestBuffer[0]=4 # Protocol.txt says with type 04 the time can be set on the device
        # put time in array
        t=math.floor(time.time())-self.TIME_OFFSET
        tb=t.to_bytes(4,byteorder='little')

        for i in range(0,4):
            self.requestBuffer[i+1]=tb[i]
        # The created buffer will tell the BS-XX0 to ge ready for a time setting.
        # the buffer containts the type 4 message and the datetime in u32le format
        # send data
        try:
            device.write(device.outAddress,self.requestBuffer,1000) # write to device at defined addres, write the buffer with time data ,timeout is 1000s
            device.read(device.inAddress,64,1000) # read at device address,get the 64 byte long message, timeout is 1000s
            device.lastTimeSync=int(time.time())  # set the actuel time since when the last sync has been performed
        except Exception as e:
            logging.error("Error setting time: %s",e)

# Mehtod will delete the internal flash data of the Logger. this done by preparing the buffer and send it to the logger

    def deleteDeviceData(self,device):
        logging.debug("deleting internal Flash data of USB device at Bus %d Address %d Port Number %d" % (device.bus,device.address,device.port_number))
        # set mode
        self.clearRequestBuffer()
        self.requestBuffer[0]=0x0d # this mode will delete the flash memory of the device 
        try:
            device.write(device.outAddress,self.requestBuffer,1000)
            device.read(device.inAddress,64,1000)
            device.lastTimeDelete=int(time.time())
        except Exception as e:
            logging.error("Error deleting flash: %s",e)


    def registerDataListener(self, dataListener):
        if isinstance(dataListener,DataListener):
            logging.debug("Registering DataListener %s",type(dataListener).__name__)
            self.listeners.append(dataListener)

    def unregisterDataListener(self, dataListener):
        try:
            self.listeners.remove(dataListener)
        except:
            logging.debug("Unable to deregister DataListener");

# Method checks for the length of device.read(device.inAddress,64,1000). If the length is 10-byte it only containts
# the signal strength. If the length is 9-byte it containts Sensor ID, the raw value and the timestamp. (see Protocol.txt)

    def parseData(self,data):
        '''
        checks if raw data are valid and extracts sensor id, raw value, timestamp and if present signal strength
        all valid data tuples are returned
        '''
        datapoints=[]
        pos=-1
        logging.debug(data)
        while pos<63:
            pos +=1
            if data[pos] == 0:
                continue
            if data[pos] == 255:
                # 255 seems to be a end of data marker
                break;
                # pos += 25
                # continue
            if (data[pos] == 9 or data[pos] == 10) and pos < 55:
                # logging.debug("Parser found start mark")
                sensorid = int.from_bytes([data[pos+1],data[pos+2]], byteorder = 'little', signed=False)

                rawvalue = int.from_bytes([data[pos+3],data[pos+4]], byteorder = 'big', signed=False)
                timestamp = int.from_bytes([data[pos+5],data[pos+6],data[pos+7],data[pos+8]], byteorder = 'little', signed=False)
                signal=None
                if data[pos] == 10:
                    signal = int.from_bytes([data[pos+9]],byteorder = 'little', signed=False)

                datapoints.append({'sensorid': sensorid, 'rawvalue': rawvalue, 'timestamp': timestamp+self.TIME_OFFSET, 'signal':signal})
                # logging.info("Found Datapoint from sensor %d with value %d" % (sensorid,rawvalue))
                pos+=data[pos]-1
                continue
            if (data[pos] == 11 or data[pos] == 12) and pos < 53:
                sensorid = int.from_bytes([data[pos+1],data[pos+2],data[pos+3],data[pos+4]], byteorder = 'little', signed=False)

                rawvalue = int.from_bytes([data[pos+5],data[pos+6]], byteorder = 'big', signed=False)
                timestamp = int.from_bytes([data[pos+7],data[pos+8],data[pos+9],data[pos+10]], byteorder = 'little', signed=False)
                signal=None
                if data[pos] == 12:
                    signal = int.from_bytes([data[pos+11]],byteorder = 'little', signed=False)
                if self.detectUnknownSensors and sensorid not in self.sensors:
                    self.addSensor(sensorid)

                datapoints.append({'sensorid': sensorid, 'rawvalue': rawvalue, 'timestamp': timestamp+self.TIME_OFFSET, 'signal':signal})
                # logging.info("Found Datapoint from sensor %d with value %d" % (sensorid,rawvalue))
                pos+=data[pos]-1
                continue

            # logging.debug("Parser: Nothing found at pos %d"%pos)
        return datapoints


# Method to extract the data. It starts by first if any listeners are currently up.
# Then checks when was the last time the time has been set on the Logger.
# It also resets the internal flash every day.
# It prepares the needed buffer message in this case starts the buffer with type-03 (see Protokol.txt). This will trigger
# the logger to request the data from the sensors.
# The data are then ask back with by reading the Logger buffer rawdata=dev.read(dev.inAddress,64,1000)

    def loop(self):
        '''
        constantly reads data from TL-X00 devices as long as DataListeners are registered.
        Stops reading when the last Listener deregisters.
        '''
        self.clearRequestBuffer()

        while len(self.listeners) > 0:
            for dev in self.devices:
                logging.debug("Polling device at Bus %d Address %d Port Number %d" % (dev.bus,dev.address,dev.port_number))
                # do time sync every 900 sec
                if int(time.time()) - dev.lastTimeSync > 900:
                    self.setTime(dev)

                # delete internal flash every day # todo: make interval configurable or count entries
                if int(time.time()) - dev.lastTimeDelete > 86400:
                    self.deleteDeviceData(dev)

                readcount=0
                founddata=0
                while True:
                    try:
                        logging.debug("write and read data from device")
                        self.clearRequestBuffer()
                        self.requestBuffer[0]=3

                        dev.write(dev.outAddress, self.requestBuffer,1000) # send request to read the sensors
                        time.sleep(0.01)
                        rawdata=dev.read(dev.inAddress,64,1000) # request the result from logger
                        if rawdata[0]==0 and rawdata[1]==0:
                            # no new data
                            break
                        dev.lastTimeDataRead = int(time.time()) # store new time of new retrieved data
                        datapoints = self.parseData(rawdata) # method to get process buffer data into usable data
                        # notify listeners
                        for datapoint in datapoints:
                            sensorid=str(datapoint["sensorid"])
                            if sensorid not in self.sensors:
                                detected_sensor=self.detectSensor(sensorid)
                                if detected_sensor != False:
                                    if self.validateSensorData(datapoint, detected_sensor):
                                        self.addSensor(detected_sensor)
                            if sensorid in self.sensors:
                                sensor=self.sensors[sensorid]
                                if self.validateSensorData(datapoint, sensor):
                                    for l in self.listeners:
                                        l.onNewData(datapoint, sensor) # invoke method to share new data to the listerners
                        founddata += len(datapoints)
                        readcount += 1
                        if founddata == 0 and readcount > 5:
                            raise Exception('device gives nonsense data')
                        elif founddata > 0:
                            dev.deviceErrors = 0
                        # sleep again before polling device
                        time.sleep(0.01)
                    except Exception as e:
                        raise
                        logging.info("Unable to read new data: %s" % e)
                        # logging.debug(traceback.format_exc())
                        dev.deviceErrors += 1
                        if dev.deviceErrors > 10 :
                            logging.warn("Too many errors. Removing device on Bus %d Address %d Port Number %d" % (dev.bus,dev.address,dev.port_number))
                            self.devices.remove(dev) # untested!
                        break
            # do not busy poll. Sleep one second
            logging.debug("sleeping")
            time.sleep(4)
            if math.floor(time.time()) > self.lastDeviceCheck + 60:
                logging.debug("Checking for new Devices")
                if self.checkForNewDevices() :
                    self.findDevices()
                    self.initializeDevices()
