import gc
import time
version_date  = "10-Mar-2022"
gc.collect()

from machine import Pin, soft_reset, freq, UART

freq(250000000)

GP23 = Pin(23, Pin.OUT)
GP23.value(1)

import json
import io
from wave_gen import *

led = Pin(25, Pin.OUT)

uart = UART(0, baudrate=9600, tx=12, rx=13)

# define wave with default values
# wave values will be updated based on input from remote UI
wave = {"func" : "none",
        "frequency" : 2000,
        "amplitude" : 0.48,
        "offset" : 0.5,
        "phase" : 0,
        "replicate" : 1,
        "pars" : [0.2, 0.4, 0.2],
        "maxsamp" : 512,
        }

# maxsamp must be a multiple of 4. 


# AWG_status flag
# status:   Meaning:
# -------   --------
# stopped     generator output stopped, new set up trigger is allowed, initialization status
# calc wave   generetor set up is trigger, wave form is calculated, no further trigger is allowed
# running     calculation finished, generator output active, new set up trigger is allowed
# -- init --  intitialization, generator not yet started using start button

AWGstat = {"AWG_status" : "- init -",
        "nsamp" : 0,
        "F_out" : 0,
        }

# Connection status to Remote UI
Conn_stat = {"version" : version_date,
            "connection" : "not connected",
            "CPU" : str(freq()),
            }


# Map function name to function
Function = {"sine" : sine,
            "pulse" : pulse,
            "gauss" : gaussian,
            "sinc" : sinc,
            "expo" : exponential,
            "noise" : noise}

# make buffers for the waveform. Here we reserve the max number of bytes
# The Remote UI can transmit smaller number of buffer bytes to be used for calculation
# large buffers give better results but are slower to fill
wavbuf={}
wavbuf[0]=bytearray(4096)
wavbuf[1]=bytearray(4096)

# define simple communication functions

in_char=""
in_text=""
out_text=""
Handshake_char = "="

def connect():
    in_char = "0"
    in_text =  ""
    
    while in_char != Handshake_char:
        try :
            in_char = uart.read(1).decode("ASCII")
            print(in_char)
        except:
            in_char = None
        
        if in_char is not None:
            in_text += in_char
    
    return in_text.strip()
    
def send(out_file):
    data = json.dumps(out_file)
    uart.write(data + "\n")
    time.sleep(0.1)

def receive():
    bytes_in = uart.read()
    message = b''
    while True:
        if uart.any():
            bytes_in = uart.read(1)
            
            if bytes_in == b'\r':
                break
            if bytes_in is not None:
                message += bytes_in
    
    response = json.load(io.BytesIO(message))
    print(response)
    return response

def blink(number):
    blink = number * 2
    for _ in range (blink):
        led.toggle()
        time.sleep_ms(150)

try:
    blink(1)
    
    connected = 0
    
    while not connected:
        
        text = connect()
        
        if text == "=":
            Conn_stat["connection"] = "READY"
            Conn_stat["version"] = version_date
            send(Conn_stat)
            connected = 1
    
    blink(2)
    
    while True:
        response = receive()        
        if response["command"] == "setup":
            
            if response["func"] == "sine":
                wave["func"] = Function[response["func"]]
                wave["pars"] = response["pars"].replace("'", "")
            elif (response["func"] == "pulse1"):
                wave["func"] = Function["pulse"]
                wave["pars"] = [0, 0.5, 0]
            elif (response["func"] == "pulse2":
                wave["func"] = Function["pulse"]
                wave["pars"] = [1, 0, 0]

            wave["frequency"] = response["frequency"]
            wave["amplitude"] = response["amplitude"]
            wave["offset"] = response["offset"]
            wave["phase"] = response["phase"]
            wave["replicate"] = response["replicate"]
            wave["maxsamp"] = response["maxsamp"]
            
            AWGstat["AWG_status"]="calc wave"
            setup_status = setupwave(wavbuf[0],wave)
            # setupwave returned to main program
            print(setup_status)
            # setupwave returns AWG status, nsamp and Frequency out
            AWGstat["AWG_status"] = setup_status[0]
            AWGstat["nsamp"] = setup_status[1]
            AWGstat["F_out"] = setup_status[2]           
            # send status to RemoteUI
            #send(AWGstat)
            # signal running AWG
            blink(4)
            
            
        elif response["command"] == "stop":
            AWGstat["AWG_status"]="stopped"
            AWGstat["nsamp"] = 0
            AWGstat["F_out"] = 0

            # stop the generator output and send status to RemoteUI
            stopDMA()

            send(AWGstat)
        
        elif response["command"] == "file":
            AWGstat["AWG_status"]="command: file not implemented"
            AWGstat["nsamp"] = 0
            AWGstat["F_out"] = 0

            send(AWGstat)
        
        elif response["command"] == "disconnect":
            AWGstat["AWG_status"]="connection reset"
            AWGstat["nsamp"] = 0
            AWGstat["F_out"] = 0

            # stop the generator output, send status to RemoteUI and restart the AWG
            stopDMA()

            send(AWGstat)

            soft_reset()

        else:
            AWGstat["AWG_status"]="error"
            AWGstat["nsamp"] = 0
            AWGstat["F_out"] = 0

            send(AWGstat)
            
except KeyboardInterrupt:
    Conn_stat["version"]  = "0.0.0"
    Conn_stat["connection"] = "closed"
    send(Conn_stat)
    connected = 0
    
except Exception as e:
    led.on()
    Conn_stat["version"]  = "mainlopp crashed"
    Conn_stat["connection"] = e
    print(Conn_stat)
    send(Conn_stat)
    connected = 0

finally:
    print("0: finally")
    #soft_reset()