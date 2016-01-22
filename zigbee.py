import logging
from uuid import uuid1
from time import sleep
from datetime import timedelta, datetime

try:
    from xbee import ZigBee
except ImportError:
    ZigBee = None


DOMAIN = "zigbee"
REQUIREMENTS = ("xbee", "pyserial")

CONF_DEVICE = "device"
CONF_BAUD = "baud"

DEFAULT_DEVICE = "/dev/ttyUSB0"
DEFAULT_BAUD = 9600

RX_TIMEOUT = timedelta(seconds=10)

log = logging.getLogger(__name__)


# Service to set states on ZigBee modules
# Service to request state from ZigBee modules
# Event for incoming state notifications

ser = None
device = None


def setup(hass, config):
    global device
    global ser
    global ZigBee

    from serial import Serial
    from xbee import ZigBee

    device = config[DOMAIN].get(CONF_DEVICE, DEFAULT_DEVICE)
    baud = int(config[DOMAIN].get(CONF_BAUD, DEFAULT_BAUD))
    ser = Serial(device, baud)
    device = ZigBeeHelper(ser)


class ZigBeeHelper(object):
    """
    Adds convenience methods for a ZigBee.
    """
    _rx_frames = {}
    _frame_id = 1

    def __init__(self, ser):
        self._ser = ser
        self._zb = ZigBee(ser, callback=self._frame_received)

    @property
    def next_frame_id(self):
        fid = self._frame_id
        self._frame_id += 1
        if self._frame_id > 0xFF:
            self._frame_id = 1
        return chr(fid)

    def _frame_received(self, frame):
        self._rx_frames[frame["frame_id"]] = frame
        log.debug("Frame received: %s" % frame)
        # @TODO: Don't store frames for longer than the timeout period

    def get_voltage(self, dest_addr_long):
        """
        Get the input voltage to the XBee module.
        """
        frame_id = self.next_frame_id
        self._zb.remote_at(frame_id=frame_id, command="%V", dest_addr_long=dest_addr_long)
        timeout = datetime.now() + RX_TIMEOUT
        while datetime.now() < timeout:
            try:
                return self._rx_frames.pop(frame_id)
            except KeyError:
                sleep(0.1)
                continue
        log.exception("Did not receive response within configured timeout period.")
