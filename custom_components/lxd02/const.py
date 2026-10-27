"""Constants for the LX-D02 thermal receipt printer integration."""

DOMAIN = "lxd02"
NAME_PREFIX = "LX-D0"
MANUFACTURER = "Dolebo"
MODEL = "LX-D02"

DEFAULT_ENERGY = 3
DEFAULT_FEED = 0.0  # extra mm after each print; the printer already feeds 10 mm (AUTO_FEED_MM)
DEFAULT_SIZE = "normal"
DEFAULT_ALIGN = "left"
SIZES = ["small", "normal", "large"]
ALIGNS = ["left", "center", "right"]

STATUS_IDLE = "idle"
STATUS_PRINTING = "printing"
STATUS_ERROR = "error"

SERVICE_PRINT = "print"
SERVICE_FEED = "feed"

ATTR_DEVICE_ID = "device_id"
ATTR_TITLE = "title"
ATTR_TEXT = "text"
ATTR_QR = "qr"
ATTR_ICON = "icon"
ATTR_IMAGE = "image"
ATTR_SIZE = "size"
ATTR_ALIGN = "align"
ATTR_MARKDOWN = "markdown"
ATTR_COPIES = "copies"
ATTR_ENERGY = "energy"
ATTR_FEED = "feed"
ATTR_LENGTH = "length"
