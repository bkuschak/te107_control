
import socket as _socket
from enum import Enum as _Enum

BUF_CHUNK = 1024

class TempUnits(_Enum):
    C = 'C'
    F = 'F'


class Device:
    """
    Generic socket connected device
    """

    @classmethod
    def from_other_dev(cls, dev):
        """Factory function for generating a new instance of the object as a more specific subclass"""
        assert issubclass(cls, dev)
        return cls(dev.host,dev.port,conn=dev._conn,id=dev._id)

    def __init__(self, host, port=5025,*args, **kwargs):
        self._host = host
        self._port = port
        self._conn = kwargs.get('conn', _socket.create_connection((self._host,self._port)))
        self._id = kwargs.get('id', None)
        self.encoding = kwargs.get('encoding', 'ascii')
        self.EOL = b'\n'
        if self._id is None:
            self.get_id()

    def _clear_buffer(self):
        res = self._conn.recv(BUF_CHUNK)
        while res:
            res = self._conn.recv(BUF_CHUNK)

    def _readline(self):
        msg = bytearray(BUF_CHUNK)
        self._conn.recv_into(msg,BUF_CHUNK)
        while msg[:-1] != ord(self.EOL):
            msg.extend(self._conn.recv(BUF_CHUNK))
        return msg.decode(self.encoding).strip()

    def send_cmd(self,cmd:str):
        self._conn.send(cmd.encode(self.encoding)+self.EOL)

    def get_id(self):
        self._clear_buffer()
        self.send_cmd('*IDN?')
        id = self._conn.recv(BUF_CHUNK).strip()
        self._id = id
        return id 

    def __del__(self):
        self._conn.close()

class F4TController (Device):
    def __init__(self, set_point:float=22.0, units:TempUnits=TempUnits.C, profile:int=1,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.set_point = set_point
        self.temp_units = units
        self.current_profile = profile
    
    def get_units(self):
        self._clear_buffer()
        self.send_cmd(':UNIT:TEMPERATURE?')
        resp = self._readline()
        self.temp_units = TempUnits(resp)        

    def set_units(self, units:TempUnits=None):
        if units is None:
            units = self.temp_units
        self.send_cmd(':UNITS:TEMPERATURE {}'.format(units.value))

    def select_profile(self, profile:int):
        # assert profile =< 40 and profile >= 1
        self.send_cmd(':PROGRAM:NUMBER {}\n'.format(profile))
    
    def run_profile(self):
        self.send_cmd(':PROGRAM:SELECTED:STATE START\n')

    def stop_profile(self):
        self.send_cmd(':PROGRAM:SELECTED:STATE STOP\n')

    def get_temperature(self):
        pass