from time import sleep as _sleep
from time import monotonic as _monotonic
from time import time as _time
import socket as _socket
from enum import StrEnum as _StrEnum
from atexit import register, unregister

# Buffer size to scan for when recieveing over the socket 
BUF_CHUNK = 10

class TempUnits(_StrEnum):
    """
    Enumeration class to represent Temperature Units of the controller
    """
    C = 'C'
    F = 'F'

class RampScale(_StrEnum):
    """
    Enumeration class to represent The timescale for the Ramp commands of to controller
    """
    MINUTES = 'MINUTES'
    HOURS = 'HOURS'

class RampAction(_StrEnum):
    """
    Enumeration class to represent the Ramp action of to controller.
    """
    OFF = 'OFF'                 # ramp instantly to setpoint
    STARTUP = 'STARTUP'         # ramp to setpoint at power on
    SETPOINT = 'SETPOINT'       # ramp to setpoint when it changes
    BOTH = 'BOTH'               # ramps on poweron or change of setpoint

class Device:
    """
    Generic socket connected device
    """
    @classmethod
    def from_other_dev(cls, dev):
        """Factory function for generating a new instance of the object as a more specific subclass"""
        assert issubclass(cls, dev)
        return cls(dev.host,dev.port,conn=dev._conn,id=dev._id)

    def __init__(self, host, port=5025,timeout=None,*args, **kwargs):
        self._host = host
        self._port = port
        self._conn = None
        self.timeout = timeout
        # print('making conn {}:{}'.format(host,port))
        self._conn = kwargs.get('conn', _socket.create_connection((self._host,self._port),timeout=timeout))
        self._id = kwargs.get('id', None)
        self._debug = kwargs.get('debug', False)
        self.encoding = kwargs.get('encoding', 'ascii')
        self.EOL = b'\n'
        if self._id is None:
            self.get_id()
        register(self._conn.close)

    def _clear_buffer(self):
        self._conn.settimeout(self.timeout)
        try:
            res = self._conn.recv(BUF_CHUNK)
            print(res)
            # while res:
            # res = self._conn.recv(BUF_CHUNK)
        except _socket.timeout:
            pass

    def _readline(self):
        msg = b'FAILED'
        try:
            msg = bytearray(self._conn.recv(BUF_CHUNK))
            # print(msg)
            while msg[-1] != ord(self.EOL):
                # print('next chunk')
                msg.extend(self._conn.recv(BUF_CHUNK))
                # print(msg)
        except _socket.timeout:
            pass
        # print('return')
        rx = msg.decode(self.encoding).strip()
        if self._debug: print('RX: {}'.format(rx))
        return rx

    def send_cmd(self,cmd:str):
        if self._debug: print('TX: {}'.format(cmd))
        self._conn.send(cmd.encode(self.encoding)+self.EOL)

    def get_id(self):
        self._clear_buffer()
        self.send_cmd('*IDN?')
        self._id = self._readline()
        return self._id 

    def __del__(self):
        if self._conn:
            unregister(self._conn.close)
            self._conn.close()

class F4TController (Device):
    def __init__(self, set_point:float=22.0, units:TempUnits=TempUnits.C, profile:int=1, cascade_option=False, *args,**kwargs):
        super().__init__(*args,**kwargs)
        self.set_point = set_point
        self.temp_units = units
        self.current_profile = profile
        self.cascade_option = cascade_option
        if self.timeout is None:
            self.timeout = 1.5
        self.profiles = {}
        # TODO Decode the part number so we know if we need to use Cascade option commands or not.
        self.cascade_init()
    
    def get_profiles(self):
        # doesnt work if profile is running
        for i in range(1,40):
            self.select_profile(i)
            _sleep(0.5)
            self.send_cmd(':PROGRAM:NAME?')
            _sleep(0.5)
            name = self._readline().strip().replace('"','')
            # print(name)
            if name:
                self.profiles[i] = name
            else:
                break

    def get_units(self):
        self._clear_buffer()
        self.send_cmd(':UNIT:TEMP?')
        _sleep(0.2)
        resp = self._readline()
        self.temp_units = TempUnits(resp)        
        return self.temp_units

    def set_units(self, units:TempUnits=None):
        if units is None:
            units = self.temp_units
        self.send_cmd(':UNIT:TEMP {}'.format(units.value))
        _sleep(0.2)
        self._readline()

    def set_ramp_action(self,action,cloop=1):
        action = RampAction(action)
        self.send_cmd(':SOURCE:CLOOP{}:RACTION {}'.format(cloop,action))
        _sleep(0.2)
        self._readline()

    def set_ramp_scale(self,ramp_scale,cloop=1):
        scale = RampScale(ramp_scale)
        self.send_cmd(':SOURCE:CLOOP{}:RSCALE {}'.format(cloop,scale))
        _sleep(0.2)
        self._readline()

    def set_ramp_rate(self,ramp_rate,cloop=1):
        self.send_cmd(':SOURCE:CLOOP{}:RRATE {}'.format(cloop,ramp_rate))
        _sleep(0.2)
        self._readline()

    def set_ramp_time(self,ramp_time,cloop=1):
        self.send_cmd(':SOURCE:CLOOP{}:RTIME {}'.format(cloop,ramp_time))
        _sleep(0.2)
        self._readline()

    def select_profile(self, profile:int):
        # assert profile =< 40 and profile >= 1
        self.send_cmd(':PROGRAM:NUMBER {}'.format(profile))
    
    def run_profile(self):
        self.send_cmd(':PROGRAM:SELECTED:STATE START')

    def stop_profile(self):
        self.send_cmd(':PROGRAM:SELECTED:STATE STOP')

    def get_temperature(self,cloop=1):
        # Cascade option requires use of different commands
        if self.cascade_option:
            # OUTER is the DUT sensor
            # INNER is the air sensor
            # We're not using DUT sensor at this time, so just return air temp
            self.send_cmd(':SOURCE:CASCADE{}:INNER:PVALUE?'.format(cloop))
        else:
            self.send_cmd(':SOURCE:CLOOP{}:PVALUE?'.format(cloop))
        _sleep(0.2)
        return float(self._readline())

    def get_temperature_setpoint(self,cloop=1):
        # Cascade option requires use of different commands
        if self.cascade_option:
            self.send_cmd(':SOURCE:CASCADE{}:SPOINT?'.format(cloop))
        else:
            self.send_cmd(':SOURCE:CLOOP{}:SPOINT?'.format(cloop))
        _sleep(0.2)
        return float(self._readline())

    def cascade_init(self, cloop=1):
        # Cascade option needs some initialization.
        if self.cascade_option:
            # For now ignore the DUT temperature.  Just control the air temp, like 
            # the standard F4T does.
            self.set_cascade_air_control()
            self.send_cmd(':SOURCE:CASCADE{}:FUNC DEVIATION'.format(cloop))
            _sleep(0.2)
            self._readline()
            self.send_cmd(':SOURCE:CASCADE{}:RANGE:LOW 10'.format(cloop))
            _sleep(0.2)
            self._readline()
            self.send_cmd(':SOURCE:CASCADE{}:RANGE:HIGH 10'.format(cloop))
            _sleep(0.2)
            self._readline()
            self.send_cmd(':SOURCE:CASCADE{}:SSPOINT:CONTROL OFF'.format(cloop))
            _sleep(0.2)
            self._readline()
            self.send_cmd(':SOURCE:CASCADE{}:CONTROL BOTH'.format(cloop))
            _sleep(0.2)
            self._readline()

    def set_cascade_air_control(self, on=True):
        # Not using cascade for DUT control. Just control the air temperature by default.
        # Note that air control is off at power on.
        if self.cascade_option:
            # KEY1 is the 'air control' key. No way to turn it on, so need to 
            # check current state and then toggle if needed.
            while True:
                self.send_cmd(':KEY1?')
                _sleep(0.2)
                resp = self._readline()
                if on and resp == 'ON':
                    return
                if not on and resp == 'OFF':
                    return
                self.send_cmd(':KEY1 PRESS')
                _sleep(0.2)

    def set_temperature(self,temp,cloop=1):
        # Cascade option requires use of different commands.
        if self.cascade_option:
            self.send_cmd(':SOURCE:CASCADE{}:SPOINT {} '.format(cloop,temp))
        else:
            self.send_cmd(':SOURCE:CLOOP{}:SPOINT {}'.format(cloop,temp))
        _sleep(0.2)

    def query_input_error(self, cloop=1):
        # Cascade option requires use of different commands.
        if self.cascade_option:
            self.send_cmd(':SOURCE:CASCADE{}:OUTER:ERROR?'.format(cloop))
        else:
            self.send_cmd(':SOURCE:CLOOP{}:ERROR?'.format(cloop))
        _sleep(0.2)
        return self._readline()
 
    def is_done(self,ouput_num):
        self.send_cmd(':OUTPUT{}:STATE?'.format(ouput_num))
        _sleep(0.2)
        resp = self._readline()
        status = None
        if resp == 'ON':
            status = True
        elif resp == 'OFF':
            status = False
        return status

    def set_output(self,output_num,state):
        self.send_cmd(':OUTPUT{}:STATE {}'.format(output_num,state))
 

if __name__ == "__main__":

    # Simple example.
    # Run a fixed number of cycles, with no ramp control.
    # Dwell for a fixed amount of time after setting low and high setpoints.
    # Temperatures in deg C.  Times in minutes.
    # host is name or IP address of the controller.
    # Set cascade_option=True if the F4T has cascade option installed.
    def run_cycles( host='100.115.106.129', cascade_option=False, 
                    num_cycles=100, low_temp=-40, high_temp=85, 
                    time_at_low_temp=60, time_at_high_temp=60, 
                    logfile='chamber_log.txt'):
        debug = False
        #debug = True

        # Connect to chamber controller
        print('Connecting to', host, '...')
        chamber = F4TController(host=host, timeout=3,
                                cascade_option=cascade_option, debug=debug)
        chamber.set_units(TempUnits.C)
        print('Chamber temperature units set to:', chamber.get_units())

        # No ramping. Maximum rate of change.
        chamber.set_ramp_action(RampAction.OFF)
        
        # Log chamber temps to file.
        log = None
        if logfile != None:
            print('Logging temperatures to file:', logfile)
            log = open(logfile, 'a')

        # Sweep across temperatures. 
        # Just use fixed times, don't delay based on actual temperature.
        for i in range(num_cycles):
            print('Cycle number', i+1, 'of', num_cycles)

            # Goto low temperature setpoint.
            print('Setting chamber setpoint:', low_temp)
            chamber.set_temperature(low_temp)

            # Delay until ready to go to high temp setpoint
            print('Delaying for', time_at_low_temp, 'minutes')
            timeout = _monotonic() + time_at_low_temp*60
            while _monotonic() < timeout:
                temp = chamber.get_temperature()
                print('Current temperature:', temp)
                if log:
                    log.write('{} {}\n'.format(_time(), temp))
                    log.flush()
                _sleep(5)

            # Goto high temperature setpoint.
            print('Setting chamber setpoint:', high_temp)
            chamber.set_temperature(high_temp)

            # Delay until ready to go to low temp setpoint
            print('Delaying for', time_at_high_temp, 'minutes')
            timeout = _monotonic() + time_at_high_temp*60
            while _monotonic() < timeout:
                temp = chamber.get_temperature()
                print('Current temperature:', temp)
                if log:
                    log.write('{} {}\n'.format(_time(), temp))
                    log.flush()
                _sleep(5)

        # Cycles complete. Goto room temperature.
        print('Setting chamber setpoint:', 20)
        chamber.set_temperature(20)

        # Delay 10 minutes to allow temperature to settle
        print('Delaying for', 10, 'minutes')
        timeout = _monotonic() + 10*60
        while _monotonic() < timeout:
            temp = chamber.get_temperature()
            print('Current temperature:', temp)
            if log:
                log.write('{} {}\n'.format(_time(), temp))
                log.flush()
            _sleep(5)

        log.close()
        return

    # Example usage:
    #run_cycles(num_cycles=100, cascade_option=True)
    #run_cycles(host='100.115.106.131', num_cycles=2, low_temp=25, high_temp=27,
               #time_at_low_temp=1, time_at_high_temp=1,
               #cascade_option=False)
    run_cycles(host='100.115.106.129', num_cycles=2, low_temp=18, high_temp=22,
               time_at_low_temp=5, time_at_high_temp=5,
               cascade_option=True)
    exit(0)

