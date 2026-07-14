"""Serial-port opener that does not reset the node.

ESP32 devkits wire DTR/RTS to EN/GPIO0 for auto-flashing; pyserial
asserts both on open, so a plain Serial(port, baud) power-cycles the
board. In the field that silently restarts the 300 s baseline
calibration every time anyone connects for diagnostics or capture.

Configuring the (unopened) port object with dtr/rts deasserted first
makes open() leave the control lines alone: the node keeps running,
uptime keeps climbing, calibration state survives the connection.
"""
import serial


def open_serial(port, baud, timeout=0.2):
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = timeout
    ser.dtr = False          # EN stays high — no reset on open
    ser.rts = False          # GPIO0 stays high — no bootloader entry
    ser.open()
    return ser
