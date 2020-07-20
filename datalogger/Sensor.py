'''
Created on 23.11.2017

@author: Florian Gleixner
@license: pylarexx is licensed under the Apache License, version 2, see License.txt

'''

import logging
import xml.etree.ElementTree
import sys
import os
from pprint import pformat

class Sensor(object):
    '''
    Sensor base class for datalogger
    '''
    def __init__(self, sensorid):
        '''
        sensorid is mandatory
        '''
        self.id = str(sensorid) # since probably not every id is numeric
        self.name = self.id
        self.displayid = self.id
        self.type = "unknown"
        self.manufacturerType = "unknown"
        self.unit = "unknown"
        self.calibrationValues = {}

    def setName(self,name):
        self.name = name
        return self

    def setType(self,sensortype):
        self.type = sensortype
        return self

    def setManufacturerType(self,mftype):
        self.manufacturerType = mftype
        return self

    def setUnit(self, unit):
        self.unit = unit
        return self


    def rawToCooked(self, raw):
        raise NotImplementedError

    def calibrate(self, calibrationValues):
        '''
        provide calibration parameters as a dictionary. The implementation of the sensor
        is responsible to read the calibration values
        '''
        self.calibrationValues = calibrationValues
        return self

class ArexxSensorDetector:

    arexxDeviceInfo = []

    def __init__(self):
        super().__init__()
        if len(ArexxSensorDetector.arexxDeviceInfo) == 0:
            self.readDeviceXML()

    def detectDevice(self,sensor_id):
        for dt in ArexxSensorDetector.arexxDeviceInfo:
            if int(sensor_id) & dt['m1'] == dt['m2']: # the magic behind m1 and m2
                displayid = int(sensor_id) & dt['dm']
                newSensor = ArexxSensor(sensor_id,displayid,dt['manufacturerType'],dt['type'], dt['unit'], dt['vLo'], dt['vUp'], dt['p0'], dt['p1'], dt['p2'])
                return newSensor
        return False

    def readDeviceXML(self):
        # read device.xml and parse it.
        logging.info("Reading deviceinfo.xml")
        try:

            devxml = xml.etree.ElementTree.parse('deviceinfo.xml').getroot()

            # devicetypes = devxml.find('devicetypes')
            for dt in devxml.findall('devicetype'):
                dtype=dt.find('type').text
                unit=dt.find('unit').text
                m1=int(dt.find('m1').text,16)
                m2=int(dt.find('m2').text,16)
                dm=int(dt.find('dm').text,16)
                vLo=float(dt.find('vLo').text)
                vUp=float(dt.find('vUp').text)
                # i=int(dt.find('i').text)
                p0=float(dt.find('p0').text)
                p1=0.0
                p2=0.0
                if dt.find('p1')!=None:
                    p1=float(dt.find('p1').text)
                if dt.find('p2')!=None:
                    p2=float(dt.find('p2').text)
                if dt.find('manufacturerType')!=None:
                    manufacturerType=dt.find('manufacturerType').text
                else:
                    manufacturerType="Unknown"

                ArexxSensorDetector.arexxDeviceInfo.append({'type': dtype, 'unit': unit, 'm1': m1, 'm2': m2, 'dm': dm, 'vLo': vLo, 'vUp': vUp, 'p0': p0, 'p1':p1, 'p2':p2, 'manufacturerType': manufacturerType})

            logging.debug(pformat(ArexxSensorDetector.arexxDeviceInfo))
        except Exception as e:
            logging.error("Problem reading deviceinfo.xml: %s",e)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)


# generic autodetected Arexx Sensor
class ArexxSensor(Sensor):

    def __init__(self, sensorid, displayid,  manufacturerType, sensortype, unit, valmin, valmax, p0, p1, p2 ):
        super().__init__(sensorid)
        self.displayid=displayid
        self.setName(displayid)
        self.setManufacturerType(manufacturerType)
        self.setType(sensortype)
        self.setUnit(unit)
        self.valmin=valmin
        self.valmax=valmax
        # self.i = i # what is this for?
        self.p0 = p0
        self.p1 = p1
        self.p2 = p2
        logging.info("Created new autodetect Arexx Sensor: %s", vars(self))

    def rawToCooked(self, raw):
        c0=self.calibrationValues.get(0,0.0)
        c1=self.calibrationValues.get(1,0.0)
        c2=self.calibrationValues.get(2,0.0)
        return self.p0 +c0 + raw*(self.p1+c1) + raw*raw*(self.p2+c2)

# Compute Values from device.xml from original software
class ArexxTemperatureSensor(Sensor):

    def __init__(self, sensorid, manufacturerType, name):
        super().__init__(sensorid)
        self.setType("Temperature").setUnit("°C").setName(name).setManufacturerType(manufacturerType)

    def rawToCooked(self,raw):
        c0=self.calibrationValues.get(0,0.0)
        c1=self.calibrationValues.get(1,0.0)
        if self.manufacturerType=='TSN-TH70E':
            return -39.6 +c0 + raw*(0.01+c1)
        if self.manufacturerType=='TL-3TSN':
            return c0+raw*(0.0078125+c1)
        # fallback default
        logging.info("Set Temperature Sensor Type in config for exact values: Sensor %s" % self.id)
        t = -39.6 +c0 + raw*(0.01+c1)
        if t > -20 and t < 50:
            return t
        else:
            return c0+raw*(0.0078125+c1)

class ArexxHumiditySensor(Sensor):

    def __init__(self, sensorid, manufacturerType, name):
        super().__init__(sensorid)
        self.setType("Humidity").setUnit("%RH").setName(name).setManufacturerType(manufacturerType)

    def rawToCooked(self,raw):
        c0=self.calibrationValues.get(0,0.0)
        c1=self.calibrationValues.get(1,0.0)
        c2=self.calibrationValues.get(2,0.0)
        return -4.0 +c0 + raw*(0.0405+c1) + raw*raw*(-0.0000028+c2)
