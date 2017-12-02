'''
Created on 23.11.2017

@author: Florian Gleixner

@license: pylarexx is licensed under the Apache License, version 2, see License.txt

DataListener Objects can be added to a Logger instance by configuration of "output".
DataListener get all values from the Sensor instances through the Logger. The can write them to stdout, to file,
serve them on a tcp socket, put them in a database (not implemented) ....
'''

import logging
import socketserver
import socket
import threading

class DataListener(object):

    def __init__ (self,params):
        self.params=params
    
    def onNewData(self,data):
        raise NotImplementedError
       
       
class LoggingListener(DataListener):
    '''
    Listener that uses logging to print data. For debugging purposes
    '''     
    
    def onNewData(self,data):
        logging.info("Datapoint: sensorid %s, raw data: %d cooked: %f %s timestamp: %d from sensor %s type %s" % (data['sensorid'],data['rawvalue'],data['sensor'].rawToCooked(data['rawvalue']),data['sensor'].unit,data['timestamp'],data['sensor'].name,data['sensor'].type))
        
class FileOutListener(DataListener):
    '''
    Listener that saves Data to a file
    '''
    def __init__(self,params):
        super().__init__(params)
        self.filename = self.params.get('filename','/tmp/pylarexx.out')
        self.status='not initialized'
        self.openLogfile()
            
    def openLogfile(self):
        try:
            # TODO: close file
            self.fd = open(self.filename,'a')
            self.status='ready'
        except Exception as e:
            self.status='error'
            logging.error("FileOutListener: Unable to open file %s. Error message: %s" % (self.filename,e))

    
    def onNewData(self,data):
        if self.status != 'ready':
            self.openLogfile()
            
        if self.status == 'ready':
            if data['signal'] == None:
                signaltext="-"
            else:
                signaltext = str(data['signal'])
            self.fd.write('%d,%d,%f %s,%d,%s,%s,%s\n' % (data['sensorid'],data['rawvalue'],data['sensor'].rawToCooked(data['rawvalue']),data['sensor'].unit,data['timestamp'],signaltext,data['sensor'].name,data['sensor'].type))

class RecentValuesListener(DataListener):
    '''
    Listener holds last value from each sensor. Listener can be queried over tcp
    '''
    def __init__(self,params):
        super().__init__(params)
        self.values={}
        self.ready=False
        self.openListeningPort()
    
    def openListeningPort(self):
        # make values visible in helper class
        values=self.values
        # helper classes
        class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
            
            def setup(self):
                response=''
                for sid,data in values.items():
                    if data['signal'] == None:
                        signaltext="-"
                    else:
                        signaltext = str(data['signal'])
                    response += '%d,%f %s,%d,%s,%s,%s\n' % (sid,data['sensor'].rawToCooked(data['rawvalue']),data['sensor'].unit,data['timestamp'],signaltext,data['sensor'].type,data['sensor'].name)
                
                self.request.sendall(bytes(response,'UTF-8'))
                
                    
        class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            pass
        
        # start tcp server
        try:
            host=self.params.get('host','localhost')
            port=self.params.get('port',4711)
            logging.info("Creating TCP server at %s:%s"%(host,port))
            server = ThreadedTCPServer((host,int(port)), ThreadedTCPRequestHandler)             
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon=True
            logging.debug("Starting TCP server")
            server_thread.start()
            self.ready=True
        except Exception as e:
            logging.error("Unable to start TCP Server: %s",e)
        
    def onNewData(self,data):
        self.values[data['sensorid']] = data
        if not self.ready:
            self.openListeningPort()
            
        
        
        
        