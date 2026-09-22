client = None
DEVICE_SERIAL = None
websocketTrace = False
display_message = False
auto_reconnect = True
reconnect_timer = 60
PING_TIMER = 60

# Pool geometry (set from config; dimensions override manual POOL_VOLUME)
POOL_SHAPE = "rectangular"
POOL_LENGTH_FT = 0.0
POOL_WIDTH_FT = 0.0
POOL_DEPTH_FT = 0.0
POOL_VOLUME = 0        # gallons
POOL_SURFACE_AREA = 0  # sq ft, derived from dimensions

# Heater
HEATER_BTU = 0
OUTDOOR_TEMP_ENTITY = ""  # HA entity ID for outdoor temperature

system_info = {
	"water": "",
	"air": "",
	"system": "",
	"swc": "",
	"light": "",
	"lightColor": "",
	"lightColorName": "",
	"clientToken": "",
	"heaterSetpoint": "",
	"heaterEnabled": "",
	"timeToSetpoint": "",
	"outdoorTemp": "",
	"salinity_gl": "",
	"pumpRpm": "",
	"pumpPreset": "",
}

# VSP speed presets discovered from filt0.spdList on connection
# Each entry: {"ar": int, "name": str, "speed": int}
pump_speed_list = []
last_published = {}

# Discovered HA sensors (populated at startup)
temp_sensors = []          # list of {entity_id, friendly_name, state, unit}
chemistry_entities = {     # best-match HA entity per chemistry param
	"ph":       None,
	"orp":      None,
	"salinity": None,
	"fc":       None,
}

# Shared HA API instance (set in main.py after startup)
ha_api = None

# Outdoor temp validation result (set at startup, refreshed periodically)
outdoor_temp_validation = {
    "configured_entity": "",
    "configured_value_f": None,
    "tcx_air_f": None,
    "candidates": [],
}

# Chemistry cache — updated by background thread only, read by web routes
# Web routes must NEVER call ha_api.get_state() directly (blocks gunicorn worker)
chemistry_readings = {}   # {param: float} — latest values read from HA + TCX salinity
chemistry_results  = []   # latest recommend() output list
chemistry_last_updated = 0.0  # unix timestamp of last successful refresh

# Actual heating rate tracking: list of (timestamp_unix, temp_f) tuples
heat_history = []
HEAT_HISTORY_MAX = 20
actual_btu_estimate = 0  # rolling estimate of effective BTU based on observed rate
