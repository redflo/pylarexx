'''
Created on 23.11.2017

@author: Florian Gleixner
@license: pylarexx is licensed under the Apache License, version 2, see License.txt

'''

import logging
import xml.etree.ElementTree
import sys
import os

class Sensor(object):
    '''
    Sensor base class for datalogger
    '''
    def __init__(self, id):
        '''
        id is mandatory
        '''
        self.id = str(id) # since probably not every id is numeric
        self.name = self.id
        self.type = "unknown"
        self.manufacturerType = "unknown"
        self.unit = "unknown"
        self.calibrationValues = {}
        
    def setName(self,name):
        self.name = name
        return self
    
        
    def setType(self,type):
        self.type = type
        return self
    
    def setManufacturerType(self,type):
        self.manufacturerType = type
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


class ArexxSensor(Sensor):
    # from device.xml from original software
    arexxDeviceInfo = {}
    
    def __init__(self,id):
        super().__init__(id)
        # reading device.xml disabled at the moment. Have to ask arexx, if i may include it in this software
        # if len(ArexxSensor.arexxDeviceInfo) == 0:
        #     self.readDeviceXML()

            
                
    def readDeviceXML(self):
        # read device.xml and parse it.
        logging.info("Reading device.xml")
        try:
            ArexxSensor.arexxDeviceInfo['units']={}
            ArexxSensor.arexxDeviceInfo['devicetypes']=[]
            
            devxml = xml.etree.ElementTree.parse('device.xml').getroot()
            units = devxml.find('units')
            for unit in units.findall('unit'):
                dtype=int(unit.find('type').text)
                strName=unit.find('strName').text
                strUnit=unit.find('strUnit').text
                if unit.find('sfx'):
                    sfx=unit.find('sfx').text
                else:
                    sfx=strUnit
                ArexxSensor.arexxDeviceInfo['units'][dtype]={'type': dtype, 'strName': strName, 'strUnit': strUnit, 'sfx': sfx}
            
            devicetypes = devxml.find('devicetypes')
            for dt in devicetypes.findall('devicetype'):
                dtype=int(dt.find('type').text)
                m1=int(dt.find('m1').text,16)
                m2=int(dt.find('m2').text,16)
                dm=int(dt.find('dm').text,16)
                vLo=float(dt.find('vLo').text)
                vUp=float(dt.find('vUp').text)
                i=int(dt.find('i').text)
                p={}
                n=0
                for param in dt.findall('p'):
                    p[n]=float(param.text)
                    n+=1
                ArexxSensor.arexxDeviceInfo['devicetypes'].append({'type': dtype, 'm1': m1, 'm2': m2, 'dm': dm, 'vLo': vLo, 'vUp': vUp, 'i': i, 'p': p})
            
                
            print(ArexxSensor.arexxDeviceInfo)     
        except Exception as e:
            logging.error("Problem reading device.xml: %s",e)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)    
        
    
# Compute Values from device.xml from original software     
class ArexxTemperatureSensor(ArexxSensor):
    
    def __init__(self, id, manufacturerType, name):
        super().__init__(id)
        self.setType("Temperature").setUnit("°C").setName(name).setManufacturerType(manufacturerType)
    
    def rawToCooked(self,raw):
        c0=self.calibrationValues.get(0,0.0)
        c1=self.calibrationValues.get(1,0.0)
        if self.manufacturerType=='TSN-TH70E':
            return -39.6 +c0 + raw*(0.01+c1)
        if self.manufacturerType=='TL-3TSN':
            return c0+raw*(0.0078125+c1)
    
        
class ArexxHumiditySensor(ArexxSensor):
    
    def __init__(self, id, manufacturerType, name):
        super().__init__(id)
        self.setType("Humidity").setUnit("%RH").setName(name).setManufacturerType(manufacturerType)
    
    def rawToCooked(self,raw):
        c0=self.calibrationValues.get(0,0.0)
        c1=self.calibrationValues.get(1,0.0)
        c2=self.calibrationValues.get(2,0.0)
        return -4.0 +c0 + raw*(0.0405+c1) + raw*raw*(-0.0000028+c2)
                                                   
                                                   
                                                   
                                                   