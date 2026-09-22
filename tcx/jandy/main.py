import logging
import math
import os
import sys

from flask import Flask
from flask_restful import Api

from jandy import CONST
from jandy.ha_api import HomeAssistantAPI
from jandy.resources import Status, TCXStateControl, Reconnect, chemistry_bp, index_bp
from jandy.zodaicio import JandyTCX


def _env_int(key, default=0):
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key, default=0.0):
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


level = os.getenv("log_level", "info")
ws_trace = os.getenv("WS_Trace", "False")
autoReconnect = os.getenv("AUTO_RECONNECT", "True")
CONST.reconnect_timer = _env_int("RECONNECT_TIMER", 60)
CONST.PING_TIMER = _env_int("PING_TIMER", 60)
_ote = os.getenv("OUTDOOR_TEMP_ENTITY", "")
CONST.OUTDOOR_TEMP_ENTITY = "" if _ote.strip().lower() in ("", "null", "none") else _ote.strip()

if str(autoReconnect).upper() == "TRUE":
	CONST.auto_reconnect = True
if str(ws_trace).upper() == "TRUE":
	CONST.websocketTrace = True

log_level = logging.getLevelName(str(level).upper())
logging.basicConfig(level=log_level,
					format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
					handlers=[logging.StreamHandler(sys.stdout)])

_Logger = logging.getLogger()

jandy_username = os.getenv("JANDY_USERNAME")
jandy_password = os.getenv("JANDY_PASSWORD")
if (jandy_username == "None") or (jandy_password == "None"):
	_Logger.fatal("Jandy Username or Password not set")
	sys.exit("Jandy Username or Password not set")

# Pool geometry
CONST.POOL_SHAPE = os.getenv("POOL_SHAPE", "rectangular").lower()
L = _env_float("POOL_LENGTH_FT")
W = _env_float("POOL_WIDTH_FT")

# Depth: prefer shallow + deep end; fall back to a single average depth
shallow = _env_float("POOL_SHALLOW_FT")
deep = _env_float("POOL_DEEP_FT")
if shallow > 0 and deep > 0:
	D = (shallow + deep) / 2
	_Logger.info(f"Pool depth: shallow {shallow} ft, deep {deep} ft → average {D:.2f} ft")
else:
	D = _env_float("POOL_DEPTH_FT")

CONST.POOL_LENGTH_FT = L
CONST.POOL_WIDTH_FT = W
CONST.POOL_DEPTH_FT = D

if L > 0 and W > 0 and D > 0:
	if CONST.POOL_SHAPE == "rectangular":
		CONST.POOL_VOLUME = round(L * W * D * 7.48)
		CONST.POOL_SURFACE_AREA = round(L * W)
	elif CONST.POOL_SHAPE == "oval":
		CONST.POOL_VOLUME = round(L * W * D * 5.9)
		CONST.POOL_SURFACE_AREA = round(math.pi * (L / 2) * (W / 2))
	elif CONST.POOL_SHAPE == "round":
		r = L / 2  # L = diameter
		CONST.POOL_VOLUME = round(math.pi * r * r * D * 7.48)
		CONST.POOL_SURFACE_AREA = round(math.pi * r * r)
	elif CONST.POOL_SHAPE == "kidney":
		CONST.POOL_VOLUME = round(L * W * D * 7.0)
		CONST.POOL_SURFACE_AREA = round(L * W * 0.75)
	else:
		CONST.POOL_VOLUME = round(L * W * D * 7.48)
		CONST.POOL_SURFACE_AREA = round(L * W)
	_Logger.info(f"Pool volume calculated: {CONST.POOL_VOLUME} gal "
				 f"({CONST.POOL_SHAPE} {L}x{W}x{D:.2f} ft), "
				 f"surface area {CONST.POOL_SURFACE_AREA} sq ft")
else:
	CONST.POOL_VOLUME = _env_int("POOL_VOLUME")
	if CONST.POOL_VOLUME:
		_Logger.info(f"Pool volume (manual): {CONST.POOL_VOLUME} gal")
	else:
		_Logger.warning("Pool volume not configured — time-to-setpoint will not be published")

CONST.HEATER_BTU = _env_int("HEATER_BTU")

# Pull all HA states once at startup; feed both temperature and chemistry detectors
_startup_api = HomeAssistantAPI()
CONST.ha_api = _startup_api
_all_states = _startup_api.get_all_states()

CONST.temp_sensors = _startup_api.get_temperature_sensors(_all_states)
_Logger.info(f"Found {len(CONST.temp_sensors)} temperature sensors in HA")

# Priority: env var → saved UI selection → auto-detect
if not CONST.OUTDOOR_TEMP_ENTITY:
	try:
		import json as _json
		with open("/data/tcx_settings.json") as _f:
			_saved = _json.load(_f).get("outdoor_temp_entity", "")
		if _saved:
			CONST.OUTDOOR_TEMP_ENTITY = _saved
			_Logger.info(f"Outdoor temp entity (saved): {CONST.OUTDOOR_TEMP_ENTITY}")
	except (FileNotFoundError, Exception):
		pass

if not CONST.OUTDOOR_TEMP_ENTITY:
	detected = _startup_api.find_outdoor_temp_entity(_all_states)
	if detected:
		CONST.OUTDOOR_TEMP_ENTITY = detected
		_Logger.info(f"Outdoor temp entity (auto-detected): {CONST.OUTDOOR_TEMP_ENTITY}")
	else:
		_Logger.warning("Could not auto-detect outdoor temp entity — select one in the dashboard")
else:
	_Logger.info(f"Outdoor temp entity (configured): {CONST.OUTDOOR_TEMP_ENTITY}")

if CONST.OUTDOOR_TEMP_ENTITY:
	CONST.outdoor_temp_validation = _startup_api.validate_outdoor_temp_entity(
		CONST.OUTDOOR_TEMP_ENTITY, _all_states
	)

CONST.chemistry_entities = _startup_api.find_chemistry_entities(_all_states)
_Logger.info(f"Chemistry entities found: { {k: v['entity_id'] if v else None for k, v in CONST.chemistry_entities.items()} }")

# Run initial chemistry recommendations from HA sensor data
try:
    from jandy.resources.chemistry import run_chemistry_refresh
    run_chemistry_refresh(force=True)
except Exception as _ce:
    _Logger.debug(f"Startup chemistry refresh skipped: {_ce}")

# Publish pool configuration as HA sensors so they are available on the
# native dashboard and in automations.
if CONST.POOL_VOLUME:
    _startup_api.set_sensor(
        "sensor.tcx_pool_volume",
        CONST.POOL_VOLUME,
        unit="gal",
        friendly_name="TCX Pool Volume",
        extra_attributes={"shape": CONST.POOL_SHAPE},
    )
if CONST.POOL_SURFACE_AREA:
    _startup_api.set_sensor(
        "sensor.tcx_pool_surface_area",
        CONST.POOL_SURFACE_AREA,
        unit="ft²",
        friendly_name="TCX Pool Surface Area",
    )

CONST.client = JandyTCX(jandy_username, jandy_password)
CONST.client.jandy_auth()
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
api = Api(app)
devices = CONST.client.get_devices()

for device in devices:
	if device["device_type"] == "tcx":
		CONST.DEVICE_SERIAL = device["serial_number"]
if CONST.DEVICE_SERIAL:
	CONST.client.device_connection(CONST.DEVICE_SERIAL)
	CONST.client.ws.open()

api.add_resource(Status, '/status')
api.add_resource(TCXStateControl, '/statecontrol')
api.add_resource(Reconnect, '/tcxreconnect')
app.register_blueprint(chemistry_bp)
app.register_blueprint(index_bp)

if __name__ == "__main__":
	app.run(debug=True, use_reloader=False)
