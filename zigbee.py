import logging
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


class ZigBeeException(Exception):
    """
    One exception to rule them all. Catch this if you don't care why it failed.
    """
    pass


class ZigBeeResponseTimeout(ZigBeeException):
    pass


class ZigBeeUnknownError(ZigBeeException):
    pass


class ZigBeeInvalidCommand(ZigBeeException):
    pass


class ZigBeeInvalidParameter(ZigBeeException):
    pass


class ZigBeeTxFailure(ZigBeeException):
    pass


class ZigBeeUnknownStatus(ZigBeeException):
    pass


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


def raise_if_error(frame):
    """
    Checks a frame and raises the relevant exception if required.
    """
    if "status" not in frame or frame["status"] == "\x00":
        return
    codes_and_exceptions = {
        "\x01": ZigBeeUnknownError,
        "\x02": ZigBeeInvalidCommand,
        "\x03": ZigBeeInvalidParameter,
        "\x04": ZigBeeTxFailure
    }
    if frame["status"] in codes_and_exceptions:
        raise codes_and_exceptions[frame["status"]]()
    raise ZigBeeUnknownStatus()


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
        """
        Gets a chr() of the next valid frame ID (1 - 255), increments the
        internal _frame_id counter and wraps it back to 1 if necessary.
        """
        fid = chr(self._frame_id)
        self._frame_id += 1
        if self._frame_id > 0xFF:
            self._frame_id = 1
        try:
            del self._rx_frames[fid]
        except KeyError:
            pass
        return fid

    def _frame_received(self, frame):
        """
        Put the frame into the _rx_frames dict with a key of the frame_id.
        """
        self._rx_frames[frame["frame_id"]] = frame
        log.debug("Frame received: %s" % frame)

    def _send(self, **kwargs):
        """
        Send a frame to either the local ZigBee or a remote device.
        """
        send_function = self._zb.remote_at if "dest_addr_long" in kwargs else self._zb.at
        send_function(**kwargs)

    def _send_and_wait(self, **kwargs):
        """
        Send a frame to either the local ZigBee or a remote device and wait
        for a pre-defined amount of time for its response.
        """
        frame_id = self.next_frame_id
        kwargs.update(dict(frame_id=frame_id))
        self._send(**kwargs)
        timeout = datetime.now() + RX_TIMEOUT
        while datetime.now() < timeout:
            try:
                frame = self._rx_frames.pop(frame_id)
                raise_if_error(frame)
                return frame
            except KeyError:
                sleep(0.1)
                continue
        log.exception("Did not receive response within configured timeout period.")
        raise ZigBeeResponseTimeout()

    def get_sample(self, dest_addr_long=None):
        """
        Initiate a sample and return its data.
        """
        kwargs = dict(dest_addr_long=dest_addr_long) if dest_addr_long is not None else {}
        frame = self._send_and_wait(command="IS", **kwargs)
        if "parameter" in frame:
            return frame["parameter"][0]  # @TODO: Is there always one value? Is it always a list?
        return {}

    def get_voltage(self, dest_addr_long=None):
        kwargs = dict(dest_addr_long=dest_addr_long) if dest_addr_long is not None else {}
        return self._send_and_wait(command="%V", **kwargs)
