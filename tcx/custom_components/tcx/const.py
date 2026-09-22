"""Constants for the Jandy TCX integration.

Command shapes here mirror the /control/* form handlers in the add-on's
jandy/resources/index.py exactly, sent instead through the generic
POST /statecontrol REST endpoint the add-on also exposes.
"""

DOMAIN = "tcx"

DEFAULT_PORT = 5050
DEFAULT_SCAN_INTERVAL = 30  # seconds — matches the add-on dashboard's own refresh

CONF_HOST = "host"
CONF_PORT = "port"

# Jandy SAm iColor light program numbers -> names (jandy/api/zodaic/messageProcessor.py)
LIGHT_COLORS = {
    1: "SAm",
    2: "Party",
    3: "Romance",
    4: "Caribbean",
    5: "American",
    6: "California Sunset",
    7: "Royal",
    8: "Blue",
    9: "Green",
    10: "Red",
    11: "White",
    12: "Magenta",
}
LIGHT_COLOR_NAME_TO_NUMBER = {name: number for number, name in LIGHT_COLORS.items()}

# Typical Jandy/Zodiac variable-speed pump range. The add-on's /status payload
# does not expose the controller's actual min/max, only the current RPM.
PUMP_RPM_MIN = 600
PUMP_RPM_MAX = 3450
PUMP_RPM_STEP = 50

HEATER_SETPOINT_MIN_F = 60
HEATER_SETPOINT_MAX_F = 104
