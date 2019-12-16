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



class TLX00(object):
    '''
    This class handles USB connection and communication for Arexx TL-300 and TL-500 devices
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
    
    def readConfigFile(self,filename):
        with open(filename) as f:
            content=f.read()
            self.config=yaml.load(content)
            logging.debug(self.config)
            
        if 'sensors' in self.config:
            try:
                for sensor in self.config['sensors']:
                    sensorid=int(sensor['id'])
                    sensortype=sensor['type']
                    name=sensor['name']
                    logging.info("Adding Sensor from config file: %d %s %s"%(sensorid,sensortype,name))
                    if sensortype in ('TL-3TSN','TSN-50E','TSN-EXT44','TSN-33MN'):
                        self.sensors[sensorid]=datalogger.Sensor.ArexxTemperatureSensor(sensorid,sensortype,name)
                    elif sensortype in ('TSN-TH70E', 'TSN-TH77ext'):
                        self.sensors[sensorid]=datalogger.Sensor.ArexxTemperatureSensor(sensorid,sensortype,name)
                        self.sensors[sensorid+1]=datalogger.Sensor.ArexxHumiditySensor(sensorid+1,sensortype,name)
                    else:
                        self.addSensor(sensorid, name, sensortype)
            except Exception as e:
                logging.error('Error in config section sensors: %s',e)

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

                    
        if 'output' in self.config:
            for logger in self.config['output']:
                try:
                    loggerType = logger.get('type')
                    params= logger.get('params',{})
                    listenerClass = getattr(datalogger.DataListener,loggerType)
                    self.registerDataListener(listenerClass(params))
                except Exception as e:
                    logging.error('Error in config section output: %s',e)
                    
        if 'config' in self.config:
            if 'DetectUnknownSensors' in self.config['config']:
                self.detectUnknownSensors=bool(self.config['config']['DetectUnknownSensors'])
    
    def addSensor(self,sensorid,name='Unknown',sensortype='Unknown'):
        if sensorid%2 == 0:
            logging.info("Adding guessed Temperature Sensor")
            self.sensors[sensorid] = datalogger.Sensor.ArexxTemperatureSensor(sensorid,sensortype,name)
        if sensorid%2 == 1:
            logging.info("Adding guessed Humidity Sensor")
            self.sensors[sensorid] = datalogger.Sensor.ArexxHumiditySensor(sensorid,sensortype,name)
    
    def clearRequestBuffer(self):
        # no more than 5 bytes are written to the buffer
        for i in range(0,5):
            self.requestBuffer[i]=0
               
    def findDevices(self):
        self.lastDeviceCheck = math.floor(time.time())
        founddevices = usb.core.find(find_all= True, idVendor=0x0451, idProduct=0x3211)
        self.devices = list(founddevices)
        if self.devices is not None:
            logging.info("Found TL300/500 device(s) at ")
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
      
    def setTime(self,device):
        logging.debug("Setting time for USB device at Bus %d Address %d Port Number %d" % (device.bus,device.address,device.port_number))
        # set mode
        self.clearRequestBuffer()
        self.requestBuffer[0]=4
        # put time in array
        t=math.floor(time.time())-self.TIME_OFFSET
        tb=t.to_bytes(4,byteorder='little')
        
        for i in range(0,4):
            self.requestBuffer[i+1]=tb[i]
        # send data
        try:
            device.write(device.outAddress,self.requestBuffer,1000)
            device.read(device.inAddress,64,1000)
            device.lastTimeSync=int(time.time())
        except Exception as e:
            logging.error("Error setting time: %s",e)
    
    def deleteDeviceData(self,device):
        logging.debug("deleting internal Flash data of USB device at Bus %d Address %d Port Number %d" % (device.bus,device.address,device.port_number))
        # set mode
        self.clearRequestBuffer()
        self.requestBuffer[0]=0x0d
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
                if self.detectUnknownSensors and sensorid not in self.sensors:
                    self.addSensor(sensorid)
                    
                datapoints.append({'sensorid': sensorid, 'rawvalue': rawvalue, 'timestamp': timestamp+self.TIME_OFFSET, 'signal':signal, 'sensor': self.sensors[sensorid]})
                # logging.info("Found Datapoint from sensor %d with value %d" % (sensorid,rawvalue))
                pos+=8
                continue
            # logging.debug("Parser: Nothing found at pos %d"%pos)
        return datapoints
        
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
                
                while True:
                    self.clearRequestBuffer()
                    self.requestBuffer[0]=3   
                    try:
                        logging.debug("write and read data from device")

                        dev.write(dev.outAddress, self.requestBuffer,1000)
                        time.sleep(0.01)
                        rawdata=dev.read(dev.inAddress,64,1000)
                        if rawdata[0]==0 and rawdata[1]==0:
                            # no new data
                            break
                        dev.lastTimeDataRead = int(time.time())
                        datapoints = self.parseData(rawdata)
                        # notify listeners
                        for datapoint in datapoints:
                            for l in self.listeners:
                                l.onNewData(datapoint)
                        dev.deviceErrors = 0
                    except Exception as e:
                        logging.info("Unable to read new data: %s" % e)
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
                
                
            
              
                
                
