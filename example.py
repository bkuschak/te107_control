from time import sleep
from f4t_control import (F4TController, RampScale, TempUnits)

# setup a temperature sweep
temp_units = TempUnits['C']
start = -40
stop = 125
step = 5
ramp_time_min = 3.0
soak_time_min = 7.0
temps = range(start,stop+step,step)

# instantiate the unit
x = F4TController(host='169.254.250.143',timeout=1)

# configure unit for sweeping temperature
x.set_ramp_time(ramp_time_min)
x.set_ramp_scale(RampScale.MINUTES)
# ensure chamber is enabled:
x.set_output(1,'ON')
# ensure units 
x.set_units(temp_units)

for temp in temps:
    print('ramping to temperature {}'.format(temp))
    x.set_temperature(temp)
    # wait for ramp time to finish
    sleep(ramp_time_min*60)
    while abs(x.get_temperature() - temp) > 0.2:
        sleep(1.0)
    # begin soak
    print('beginning soak at temp {}'.format(x.get_temperature()))
    sleep(soak_time_min*60)

# turn off unit
print('completed sweep!')
x.set_output(1,'OFF')
x.set_temperature(22)
# cleanup for socket connection is handled automatically
