import json
import logging
import time

import CONST

_LOGGING = logging.getLogger()


def _water_raw_to_fahrenheit(raw):
    if isinstance(raw, dict):
        raw = raw.get("value", 0)
    result = round((raw / 10) * 9 / 5 + 32, 1)
    _LOGGING.debug(f"Water temp: raw={raw} → {result}°F  [formula: (raw/10)*9/5+32]")
    return result


def _air_raw_to_fahrenheit(raw):
    if isinstance(raw, dict):
        raw = raw.get("value", 0)
    # Same encoding as water: raw = tenths of °C
    result = round((raw / 10) * 9 / 5 + 32, 1)
    _LOGGING.debug(f"Air temp: raw={raw} → {result}°F  [formula: (raw/10)*9/5+32]")
    return result


_HEAT_LOSS_COEFF = 4.0  # BTU / (hr · ft² · °F), uncovered pool estimate


def _update_heat_history(current_temp_f):
    """Record a temperature sample and derive an actual BTU estimate."""
    now = time.time()
    CONST.heat_history.append((now, current_temp_f))
    if len(CONST.heat_history) > CONST.HEAT_HISTORY_MAX:
        CONST.heat_history.pop(0)

    # Need at least two readings with temp rising and volume known
    if len(CONST.heat_history) < 2 or not CONST.POOL_VOLUME:
        return

    oldest_t, oldest_temp = CONST.heat_history[0]
    newest_t, newest_temp = CONST.heat_history[-1]
    elapsed_hours = (newest_t - oldest_t) / 3600.0
    if elapsed_hours < (5 / 60):  # need at least 5 min of data
        return
    delta = newest_temp - oldest_temp
    if delta <= 0:
        return  # cooling or steady, don't update estimate

    observed_btu = (delta * CONST.POOL_VOLUME * 8.34) / elapsed_hours
    # Blend 70% previous estimate, 30% new observation (exponential smoothing)
    if CONST.actual_btu_estimate == 0:
        CONST.actual_btu_estimate = observed_btu
    else:
        CONST.actual_btu_estimate = round(
            0.7 * CONST.actual_btu_estimate + 0.3 * observed_btu
        )
    _LOGGING.debug(f"Actual BTU estimate updated: {CONST.actual_btu_estimate:.0f}")


def _ha_temp_to_fahrenheit(raw_state, entity_id):
    """Convert an HA temperature state string to °F, respecting the sensor's unit."""
    try:
        temp = float(raw_state)
    except (TypeError, ValueError):
        return None
    # Look up the unit from the discovered sensor list
    sensor = next(
        (s for s in CONST.temp_sensors if s["entity_id"] == entity_id), None
    )
    if sensor and sensor.get("unit") == "°C":
        temp = round(temp * 9 / 5 + 32, 1)
    return temp


def _effective_btu(ha_api):
    """Return the best available net BTU/hr for heating, accounting for heat loss."""
    base_btu = CONST.actual_btu_estimate if CONST.actual_btu_estimate else CONST.HEATER_BTU
    if not base_btu:
        return 0

    # Heat loss: surface area × coefficient × (pool_temp - outdoor_temp)
    heat_loss = 0
    outdoor_temp = None
    if CONST.OUTDOOR_TEMP_ENTITY:
        raw = ha_api.get_state(CONST.OUTDOOR_TEMP_ENTITY)
        outdoor_temp = _ha_temp_to_fahrenheit(raw, CONST.OUTDOOR_TEMP_ENTITY)
        if outdoor_temp is not None:
            CONST.system_info["outdoorTemp"] = outdoor_temp
            _LOGGING.debug(f"Outdoor temp: {outdoor_temp}°F from {CONST.OUTDOOR_TEMP_ENTITY}")
            ha_api.set_sensor(
                "sensor.tcx_outdoor_temperature",
                outdoor_temp,
                unit="°F",
                device_class="temperature",
                friendly_name="TCX Outdoor Temperature",
            )

    if outdoor_temp is not None and CONST.POOL_SURFACE_AREA:
        pool_temp = CONST.system_info.get("water")
        if isinstance(pool_temp, (int, float)):
            heat_loss = _HEAT_LOSS_COEFF * CONST.POOL_SURFACE_AREA * max(0, pool_temp - outdoor_temp)
            _LOGGING.debug(f"Heat loss estimate: {heat_loss:.0f} BTU/hr "
                           f"(outdoor {outdoor_temp}°F, pool {pool_temp}°F)")

    return max(1, base_btu - heat_loss)


def _publish_time_to_setpoint(ha_api):
    if not CONST.POOL_VOLUME or not CONST.HEATER_BTU:
        return
    current = CONST.system_info.get("water")
    setpoint = CONST.system_info.get("heaterSetpoint")
    if not isinstance(current, (int, float)) or not isinstance(setpoint, (int, float)):
        return
    delta = setpoint - current
    if delta <= 0:
        minutes = 0
    else:
        net_btu = _effective_btu(ha_api)
        if not net_btu:
            return
        minutes = round((delta * CONST.POOL_VOLUME * 8.34) / (net_btu / 60))
    CONST.system_info["timeToSetpoint"] = minutes
    ha_api.set_sensor(
        "sensor.tcx_time_to_setpoint",
        minutes,
        unit="min",
        friendly_name="TCX Time to Setpoint",
    )


def processClientToken(message):
    if "clientToken" in message["payload"]:
        _LOGGING.debug(f"Client Token: {message['payload']['clientToken']}")
        return message["payload"]["clientToken"]
    else:
        return None


def processTCXTemp(message, ha_api):
    if "air" in message:
        raw = message["air"]
        temp_f = _air_raw_to_fahrenheit(raw)
        _LOGGING.debug(f"Air temperature reading: {raw} raw -> {temp_f}°F")
        CONST.system_info["air"] = temp_f
        ha_api.set_sensor(
            "sensor.tcx_air_temperature",
            temp_f,
            unit="°F",
            device_class="temperature",
            friendly_name="TCX Air Temperature",
        )
    if "water" in message:
        raw = message["water"]
        temp_f = _water_raw_to_fahrenheit(raw)
        _LOGGING.debug(f"Water temperature reading: {raw} raw -> {temp_f}°F")
        CONST.system_info["water"] = temp_f
        _update_heat_history(temp_f)
        ha_api.set_sensor(
            "sensor.tcx_pool_temperature",
            temp_f,
            unit="°F",
            device_class="temperature",
            friendly_name="TCX Pool Temperature",
        )
        _publish_time_to_setpoint(ha_api)


def _process_vsp(filt0, ha_api):
    """Extract variable speed pump fields from filt0 and publish to HA."""
    # Store speed presets once (they don't change at runtime)
    spd_list = filt0.get("spdList", [])
    if spd_list and not CONST.pump_speed_list:
        CONST.pump_speed_list = [
            {"ar": s["ar"], "name": s["name"], "speed": s["speed"]}
            for s in spd_list
            if "ar" in s and "name" in s and "speed" in s
        ]
        _LOGGING.info(f"VSP speed presets: { {s['name']: s['speed'] for s in CONST.pump_speed_list} }")

    # Current RPM
    rpm = filt0.get("manSpd")
    if rpm is not None:
        # Determine which preset is active (match by RPM), or "Custom" for manual speeds
        preset_name = next(
            (s["name"] for s in CONST.pump_speed_list if s["speed"] == rpm), "Custom"
        ) if CONST.pump_speed_list else ""
        CONST.system_info["pumpRpm"] = rpm
        CONST.system_info["pumpPreset"] = preset_name
        _LOGGING.info(f"Pump speed: {rpm} RPM" + (f" ({preset_name})" if preset_name else ""))
        ha_api.set_sensor(
            "sensor.tcx_pump_rpm",
            rpm,
            unit="RPM",
            friendly_name="TCX Pump Speed",
            extra_attributes={"preset": preset_name, "min_rpm": filt0.get("minSpd"), "max_rpm": filt0.get("maxSpd")},
        )
        ha_api.set_sensor(
            "sensor.tcx_pump_preset",
            preset_name,
            friendly_name="TCX Pump Preset",
        )


def processFilterStatus(message, ha_api):
    status = 0
    filt0 = None

    if "filt" in message:
        filter_message = message["filt"]
        try:
            filt0 = filter_message["state"]["reported"]["filt0"]
            status = filt0.get("st", 0)
        except (KeyError, TypeError):
            return
    elif "filt0" in message:
        # Delta update — top-level filt0 key (same pattern as auxz0 for lights)
        filt0 = message["filt0"]
        status = filt0.get("st", 0)
    elif "pool" in message:
        pool = message["pool"]
        status = pool.get("st", 1)
    else:
        return

    try:
        is_on = status == 1
        _LOGGING.info(f"Pool Filter is {'on' if is_on else 'off'}")
        CONST.system_info["system"] = "ON" if is_on else "OFF"
        ha_api.set_binary_sensor(
            "binary_sensor.tcx_pump",
            is_on,
            device_class="running",
            friendly_name="TCX Pool Pump",
        )
    except Exception as e:
        _LOGGING.error(f"Error updating pump state: {str(e)}")

    # Extract VSP fields if present
    if filt0:
        try:
            _process_vsp(filt0, ha_api)
        except Exception as e:
            _LOGGING.error(f"Error processing VSP data: {str(e)}")


def processSWCStatus(message, ha_api):
    salinity = None

    if "swc" in message:
        if CONST.display_message:
            _LOGGING.debug(f"SWC Status Message: {json.dumps(message, indent=4, sort_keys=True)}")
        if "state" not in message["swc"]:
            return
        swc0 = message["swc"]["state"]["reported"].get("swc0", {})
        if "outputPcnt" in swc0:
            value = swc0["outputPcnt"]
            if value == 0 and "stdPoolPcnt" in swc0:
                value = swc0["stdPoolPcnt"]
        elif "stdPoolPcnt" in swc0:
            value = swc0["stdPoolPcnt"]
        else:
            return
        salinity = swc0.get("salinity")

    elif "swc0" in message:
        if "outputPcnt" in message["swc0"]:
            value = message["swc0"]["outputPcnt"]
            if value == 0 and "stdPoolPcnt" in message["swc0"]:
                value = message["swc0"]["stdPoolPcnt"]
        elif "stdPoolPcnt" in message["swc0"]:
            value = message["swc0"]["stdPoolPcnt"]
        else:
            return
        salinity = message["swc0"].get("salinity")
    else:
        return

    try:
        _LOGGING.info(f"Chlorine Production is set to: {value}%")
        CONST.system_info["swc"] = f"{value}%"
        ha_api.set_sensor(
            "sensor.tcx_swc_level",
            value,
            unit="%",
            friendly_name="TCX Chlorine Production",
        )
        if salinity is not None:
            # TCX reports salinity in tenths of g/L (e.g. 30 = 3.0 g/L = ~3000 ppm)
            salinity_gl = round(salinity / 10, 1)
            _LOGGING.info(f"Salinity: raw={salinity} -> {salinity_gl} g/L")
            prev_salinity = CONST.system_info.get("salinity_gl")
            CONST.system_info["salinity_gl"] = salinity_gl
            ha_api.set_sensor(
                "sensor.tcx_salinity",
                salinity_gl,
                unit="g/L",
                friendly_name="TCX Pool Salinity",
            )
            # Salinity changed — re-run chemistry recommendations using HA data
            if salinity_gl != prev_salinity:
                try:
                    from jandy.resources.chemistry import run_chemistry_refresh  # noqa: PLC0415
                    run_chemistry_refresh()
                except Exception as ce:
                    _LOGGING.debug(f"Chemistry refresh skipped: {ce}")
    except Exception as e:
        _LOGGING.error(f"Error updating SWC state: {str(e)}")


# Jandy SAm iColor light color map (cmdClr 1–12)
LIGHT_COLORS = {
    1:  "SAm",
    2:  "Party",
    3:  "Romance",
    4:  "Caribbean",
    5:  "American",
    6:  "California Sunset",
    7:  "Royal",
    8:  "Blue",
    9:  "Green",
    10: "Red",
    11: "White",
    12: "Magenta",
}


def processLightStatus(message, ha_api):
    if "zig" in message:
        try:
            if CONST.display_message:
                _LOGGING.debug(f"Light Message ZIG: {json.dumps(message, indent=4, sort_keys=True)}")
            auxz0 = message["zig"]["state"]["reported"]["auxz0"]
        except Exception as e:
            _LOGGING.error(str(e))
            return
    elif "auxz0" in message:
        _LOGGING.debug(f"Light Message AUXz0: {json.dumps(message, indent=4, sort_keys=True)}")
        auxz0 = message["auxz0"]
    else:
        return

    has_st = "st" in auxz0
    has_color = "cmdClr" in auxz0

    if not has_st and not has_color:
        return

    try:
        color_value = auxz0.get("cmdClr")
        st_value = auxz0.get("st")

        # Only update on/off state when st is explicitly present.
        # A message with only cmdClr is a color-change command mid-transition;
        # treating missing st as 0 would cause a false "off" flash in HA.
        if has_st:
            is_on = st_value == 1
            _LOGGING.info(f"Pool Light is {'On, Color: ' + str(color_value) if is_on else 'OFF'}")
            CONST.system_info["light"] = "ON" if is_on else "OFF"
            ha_api.set_binary_sensor(
                "binary_sensor.tcx_light",
                is_on,
                device_class="light",
                friendly_name="TCX Pool Light",
                extra_attributes={"color": color_value,
                                  "color_name": LIGHT_COLORS.get(color_value, "") if color_value else ""},
            )

        if has_color and color_value:
            color_name = LIGHT_COLORS.get(color_value, str(color_value))
            CONST.system_info["lightColor"] = color_value
            CONST.system_info["lightColorName"] = color_name
            ha_api.set_sensor(
                "sensor.tcx_light_color",
                color_value,
                friendly_name="TCX Pool Light Color",
                extra_attributes={"color_name": color_name},
            )
            ha_api.set_sensor(
                "sensor.tcx_light_color_name",
                color_name,
                friendly_name="TCX Pool Light Color Name",
            )
    except Exception as e:
        _LOGGING.error(f"Error updating light state: {str(e)}")


def processECMStatus(message, ha_api):
    """Process ecm0 messages.

    ecm0 = Electronically Commutated Motor — the VSP motor controller.
    It carries the same speed/preset data as filt0 (manSpd, spdList, st)
    and fires very frequently during pump operation.  We reuse _process_vsp
    so any speed change reported here is reflected in HA immediately.
    There is no wattage/power field in this message type.
    """
    ecm0 = None
    if "ecm0" in message:
        ecm0 = message["ecm0"]
    elif "ecm" in message:
        try:
            ecm0 = message["ecm"]["state"]["reported"].get("ecm0")
        except (KeyError, TypeError):
            return
    if ecm0 is None:
        return

    _LOGGING.debug(f"ECM0: st={ecm0.get('st')} manSpd={ecm0.get('manSpd')} reqSpd={ecm0.get('reqSpd')}")

    # Reuse VSP processing — ecm0 has the same spdList/manSpd structure as filt0
    try:
        _process_vsp(ecm0, ha_api)
    except Exception as e:
        _LOGGING.error(f"Error processing ECM0 VSP data: {e}")


def processHeaterStatus(message, ha_api):
    tsp = None
    if "TspBdy0" in message:
        tsp = message["TspBdy0"]
    elif "tsp" in message:
        try:
            tsp = message["tsp"]["state"]["reported"].get("TspBdy0")
        except (KeyError, TypeError):
            return
    if tsp is None:
        return

    try:
        if "waterTempSet" in tsp:
            setpoint_f = _water_raw_to_fahrenheit(tsp["waterTempSet"])
            _LOGGING.info(f"Heater setpoint: {setpoint_f}°F")
            CONST.system_info["heaterSetpoint"] = setpoint_f
            ha_api.set_sensor(
                "sensor.tcx_heater_setpoint",
                setpoint_f,
                unit="°F",
                device_class="temperature",
                friendly_name="TCX Heater Setpoint",
            )
        if "heatEnabled" in tsp:
            is_on = bool(tsp["heatEnabled"])
            _LOGGING.info(f"Heater enabled: {is_on}")
            CONST.system_info["heaterEnabled"] = "ON" if is_on else "OFF"
            ha_api.set_binary_sensor(
                "binary_sensor.tcx_heater",
                is_on,
                device_class="heat",
                friendly_name="TCX Heater",
            )
        _publish_time_to_setpoint(ha_api)
    except Exception as e:
        _LOGGING.error(f"Error updating heater state: {str(e)}")
