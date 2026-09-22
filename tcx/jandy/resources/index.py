import json
import logging
import os
import time

from flask import Blueprint, redirect, render_template, request, url_for

from jandy import CONST

_LOGGER = logging.getLogger()
index_bp = Blueprint("index", __name__)

_SETTINGS_FILE = "/data/tcx_settings.json"


def _load_persisted_settings():
    """Read settings saved by the UI from /data/tcx_settings.json."""
    try:
        with open(_SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_persisted_settings(data: dict):
    """Merge data into /data/tcx_settings.json."""
    existing = _load_persisted_settings()
    existing.update(data)
    os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(existing, f)

# ── HA state cache ─────────────────────────────────────────────────────────
# Avoids making 10+ individual HTTP calls on every dashboard page load.
# Values refresh once the TTL expires (aligned to the 30-second auto-refresh).
_HA_CACHE: dict = {}
_HA_CACHE_TTL = 20  # seconds


def _ha_get(entity_id):
    """Return cached HA state, refreshing after TTL."""
    now = time.monotonic()
    entry = _HA_CACHE.get(entity_id)
    if entry and now - entry[0] < _HA_CACHE_TTL:
        return entry[1]
    val = CONST.ha_api.get_state(entity_id) if CONST.ha_api else None
    _HA_CACHE[entity_id] = (now, val)
    return val

_TCX_SENSORS = {
    "water":          "sensor.tcx_pool_temperature",
    "air":            "sensor.tcx_air_temperature",
    "heaterSetpoint": "sensor.tcx_heater_setpoint",
    "timeToSetpoint": "sensor.tcx_time_to_setpoint",
    "swc":            "sensor.tcx_swc_level",
    "salinity_gl":    "sensor.tcx_salinity",
    "outdoorTemp":    "sensor.tcx_outdoor_temperature",
    "lightColor":     "sensor.tcx_light_color",
    "pumpRpm":        "sensor.tcx_pump_rpm",
}
# String-valued sensors — read as-is, no float conversion
_TCX_STRING_SENSORS = {
    "lightColorName": "sensor.tcx_light_color_name",
    "pumpPreset":     "sensor.tcx_pump_preset",
}
_TCX_BINARY = {
    "system":        "binary_sensor.tcx_pump",
    "light":         "binary_sensor.tcx_light",
    "heaterEnabled": "binary_sensor.tcx_heater",
}


def _send_tcx(namespace, desired):
    """Send a setState command to the TCX controller via the open websocket."""
    try:
        from jandy.api import messages
        msg = messages.setState(namespace, desired, CONST.DEVICE_SERIAL)
        if CONST.client and CONST.client.ws:
            CONST.client.ws.send_state(msg)
            _LOGGER.info(f"TCX command sent: {namespace} {desired}")
            return True
        _LOGGER.error("TCX command failed: no websocket connection")
    except Exception as e:
        _LOGGER.error(f"TCX command error: {e}")
    return False


def _read_pool_info():
    """Return system_info merged with cached HA sensor values as fallback."""
    info = dict(CONST.system_info)

    # TCX numeric sensors
    for key, entity_id in _TCX_SENSORS.items():
        if info.get(key) in ("", None):
            val = _ha_get(entity_id)
            if val not in (None, "unknown", "unavailable"):
                try:
                    info[key] = float(val)
                except ValueError:
                    info[key] = val

    # TCX string sensors (read as-is, no numeric conversion)
    for key, entity_id in _TCX_STRING_SENSORS.items():
        if info.get(key) in ("", None):
            val = _ha_get(entity_id)
            if val not in (None, "unknown", "unavailable"):
                info[key] = val

    # TCX binary sensors
    for key, entity_id in _TCX_BINARY.items():
        if info.get(key) in ("", None):
            val = _ha_get(entity_id)
            if val == "on":
                info[key] = "ON"
            elif val == "off":
                info[key] = "OFF"

    # Outdoor temp from the configured HA entity — convert °C→°F if needed,
    # then publish as sensor.tcx_outdoor_temperature so it joins the TCX sensor family
    if info.get("outdoorTemp") in ("", None) and CONST.OUTDOOR_TEMP_ENTITY:
        val = _ha_get(CONST.OUTDOOR_TEMP_ENTITY)
        if val not in (None, "unknown", "unavailable"):
            try:
                temp = float(val)
                sensor = next(
                    (s for s in CONST.temp_sensors if s["entity_id"] == CONST.OUTDOOR_TEMP_ENTITY),
                    None,
                )
                if sensor and sensor.get("unit") == "°C":
                    temp = round(temp * 9 / 5 + 32, 1)
                info["outdoorTemp"] = temp
                if CONST.ha_api:
                    CONST.ha_api.set_sensor(
                        "sensor.tcx_outdoor_temperature",
                        temp,
                        unit="°F",
                        device_class="temperature",
                        friendly_name="TCX Outdoor Temperature",
                    )
            except (TypeError, ValueError):
                pass

    # Compute time-to-setpoint if the HA sensor doesn't exist yet
    if info.get("timeToSetpoint") in ("", None):
        water = info.get("water")
        setpoint = info.get("heaterSetpoint")
        if (isinstance(water, (int, float)) and isinstance(setpoint, (int, float))
                and CONST.POOL_VOLUME and CONST.HEATER_BTU):
            delta = setpoint - water
            if delta <= 0:
                minutes = 0
            else:
                btu = CONST.actual_btu_estimate or CONST.HEATER_BTU
                outdoor = info.get("outdoorTemp")
                if isinstance(outdoor, (int, float)) and CONST.POOL_SURFACE_AREA:
                    heat_loss = 4.0 * CONST.POOL_SURFACE_AREA * max(0, water - outdoor)
                    btu = max(1, btu - heat_loss)
                minutes = round((delta * CONST.POOL_VOLUME * 8.34) / (btu / 60))
            info["timeToSetpoint"] = minutes
            # Push the computed value to HA so the sensor exists for next time
            if CONST.ha_api:
                CONST.ha_api.set_sensor(
                    "sensor.tcx_time_to_setpoint",
                    minutes,
                    unit="min",
                    friendly_name="TCX Time to Setpoint",
                )

    return info


def _read_live_chemistry():
    """Read current values from auto-detected HA chemistry entities (cached)."""
    live = {}
    for param, entity in CONST.chemistry_entities.items():
        if not entity:
            continue
        try:
            fresh = _ha_get(entity["entity_id"])
            val = float(fresh) if fresh not in (None, "unknown", "unavailable") else float(entity["state"])
            live[param] = {
                "value": val,
                "unit": entity["unit"],
                "entity_id": entity["entity_id"],
                "friendly_name": entity["friendly_name"],
            }
        except (TypeError, ValueError):
            pass
    return live


@index_bp.route("/", methods=["GET"])
def dashboard():
    return render_template(
        "index.html",
        info=_read_pool_info(),
        pool_volume=CONST.POOL_VOLUME,
        pool_shape=CONST.POOL_SHAPE,
        pool_length=CONST.POOL_LENGTH_FT,
        pool_width=CONST.POOL_WIDTH_FT,
        pool_depth=CONST.POOL_DEPTH_FT,
        heater_btu=CONST.HEATER_BTU,
        outdoor_entity=CONST.OUTDOOR_TEMP_ENTITY,
        temp_sensors=CONST.temp_sensors,
        chemistry=_read_live_chemistry(),
        chemistry_entities=CONST.chemistry_entities,
        otv=CONST.outdoor_temp_validation,
        pump_speed_list=CONST.pump_speed_list,
    )


# ── Settings ──────────────────────────────────────────────────────────────────

@index_bp.route("/settings", methods=["POST"])
def update_settings():
    entity = request.form.get("outdoor_temp_entity", "").strip()
    if entity:
        CONST.OUTDOOR_TEMP_ENTITY = entity
        CONST.last_published.pop("sensor.tcx_time_to_setpoint", None)
        _save_persisted_settings({"outdoor_temp_entity": entity})
        _LOGGER.info(f"Outdoor temp entity updated via UI: {entity}")
    return redirect(url_for("index.dashboard"))


# ── Controls ──────────────────────────────────────────────────────────────────

@index_bp.route("/control/pump", methods=["POST"])
def control_pump():
    state = request.form.get("state", "off")
    _send_tcx("filtration", {"pool": {"st": 1 if state == "on" else 0}})
    return redirect(url_for("index.dashboard"))


@index_bp.route("/control/pump/speed", methods=["POST"])
def control_pump_speed():
    try:
        rpm = int(request.form.get("rpm", 0))
        if rpm > 0:
            _send_tcx("filtration", {"filt0": {"manSpd": rpm}})
    except (ValueError, TypeError):
        pass
    return redirect(url_for("index.dashboard"))


@index_bp.route("/control/heater", methods=["POST"])
def control_heater():
    state = request.form.get("state", "off")
    _send_tcx("TCX", {"TspBdy0": {"heatEnabled": 1 if state == "on" else 0}})
    return redirect(url_for("index.dashboard"))


@index_bp.route("/control/light", methods=["POST"])
def control_light():
    state = request.form.get("state", "off")
    _send_tcx("zig", {"auxz0": {"st": 1 if state == "on" else 0}})
    return redirect(url_for("index.dashboard"))


@index_bp.route("/control/light/color", methods=["POST"])
def control_light_color():
    try:
        color = int(request.form.get("color", 0))
        if 1 <= color <= 12:
            _send_tcx("zig", {"auxz0": {"cmdClr": color}})
    except (ValueError, TypeError):
        pass
    return redirect(url_for("index.dashboard"))


@index_bp.route("/control/setpoint", methods=["POST"])
def control_setpoint():
    try:
        temp_f = float(request.form.get("temp_f", 0))
        if 60 <= temp_f <= 104:
            raw = round((temp_f - 32) * 5 / 9 * 10)
            _send_tcx("TCX", {"TspBdy0": {"waterTempSet": raw}})
    except (ValueError, TypeError):
        pass
    return redirect(url_for("index.dashboard"))


@index_bp.route("/control/swc", methods=["POST"])
def control_swc():
    """Set salt water chlorinator output level (0–100 %)."""
    try:
        level = int(request.form.get("level", 0))
        if 0 <= level <= 100:
            _send_tcx("swc", {"swc0": {"stdPoolPcnt": level}})
    except (ValueError, TypeError):
        pass
    return redirect(url_for("index.dashboard"))
