import logging
import os

import requests

from jandy import CONST

from ha_publish import should_skip_publish

_LOGGING = logging.getLogger()

# Inside the add-on container HA is always reachable via the supervisor proxy.
# Port 80 fallback is only used if the supervisor URL is unreachable (e.g. dev/testing).
_HA_API_BASE = "http://supervisor/core/api"


class HomeAssistantAPI:
    def __init__(self):
        self._token = os.getenv("SUPERVISOR_TOKEN")
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Write helpers                                                         #
    # ------------------------------------------------------------------ #

    def set_sensor(self, entity_id, state, unit=None, device_class=None, friendly_name=None, extra_attributes=None):
        attributes = {}
        if unit:
            attributes["unit_of_measurement"] = unit
        if device_class:
            attributes["device_class"] = device_class
        if friendly_name:
            attributes["friendly_name"] = friendly_name
        if extra_attributes:
            attributes.update(extra_attributes)
        self._set_state(entity_id, state, attributes)

    def set_binary_sensor(self, entity_id, is_on, device_class=None, friendly_name=None, extra_attributes=None):
        attributes = {}
        if device_class:
            attributes["device_class"] = device_class
        if friendly_name:
            attributes["friendly_name"] = friendly_name
        if extra_attributes:
            attributes.update(extra_attributes)
        self._set_state(entity_id, "on" if is_on else "off", attributes)

    def _set_state(self, entity_id, state, attributes=None):
        state_str = str(state)
        ha_state = None
        if CONST.last_published.get(entity_id) == state_str:
            ha_state = self.get_state(entity_id)
            if should_skip_publish(CONST.last_published.get(entity_id), state_str, ha_state):
                return
        url = f"{_HA_API_BASE}/states/{entity_id}"
        payload = {"state": state_str}
        if attributes:
            payload["attributes"] = attributes
        try:
            resp = requests.post(url, json=payload, headers=self._headers, timeout=5)
            resp.raise_for_status()
            CONST.last_published[entity_id] = state_str
            _LOGGING.debug(f"HA state updated: {entity_id} = {state_str}")
        except Exception as e:
            _LOGGING.error(f"Failed to update HA state {entity_id}: {e}")

    # ------------------------------------------------------------------ #
    # Read helpers                                                          #
    # ------------------------------------------------------------------ #

    def get_state(self, entity_id):
        url = f"{_HA_API_BASE}/states/{entity_id}"
        try:
            resp = requests.get(url, headers=self._headers, timeout=5)
            if resp.status_code == 404:
                return None  # entity not yet created; not an error
            resp.raise_for_status()
            return resp.json().get("state")
        except Exception as e:
            _LOGGING.error(f"Failed to read HA state {entity_id}: {e}")
            return None

    def get_all_states(self):
        url = f"{_HA_API_BASE}/states"
        try:
            resp = requests.get(url, headers=self._headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _LOGGING.error(f"Failed to fetch HA states: {e}")
            return []

    # ------------------------------------------------------------------ #
    # Discovery                                                             #
    # ------------------------------------------------------------------ #

    def get_temperature_sensors(self, all_states=None):
        if all_states is None:
            all_states = self.get_all_states()
        sensors = []
        for s in all_states:
            attrs = s.get("attributes", {})
            if (attrs.get("device_class") == "temperature"
                    or attrs.get("unit_of_measurement") in ("°F", "°C")):
                try:
                    float(s.get("state", ""))
                except (ValueError, TypeError):
                    continue
                sensors.append({
                    "entity_id": s["entity_id"],
                    "friendly_name": attrs.get("friendly_name", s["entity_id"]),
                    "state": s.get("state", ""),
                    "unit": attrs.get("unit_of_measurement", ""),
                })
        return sorted(sensors, key=lambda x: x["friendly_name"].lower())

    def find_outdoor_temp_entity(self, all_states=None):
        """Score temperature sensors and return the most likely outdoor one."""
        _OUTDOOR = ["openweathermap_temperature", "outdoor", "outside", "exterior",
                    "ambient", "openweathermap", "darksky", "met_no", "pirateweather",
                    "accuweather", "weather", "ecobee_outdoor", "nest_outdoor"]
        _INDOOR  = ["indoor", "inside", "interior", "room", "bedroom", "living",
                    "kitchen", "bathroom", "basement", "garage", "attic", "crawl",
                    "inverter", "processor", "mcu", "pcb", "handle", "extruder",
                    "bed_temperature", "battery_module", "driver_temperature",
                    "passenger_temperature"]
        _POOL    = ["pool", "water", "tcx", "spa", "hot_tub"]

        sensors = self.get_temperature_sensors(all_states)
        best_entity, best_score = None, -99

        for s in sensors:
            combined = (s["entity_id"] + " " + s["friendly_name"]).lower()
            score = 0
            for kw in _OUTDOOR:
                if kw in combined:
                    score += 3
            for kw in _INDOOR:
                if kw in combined:
                    score -= 4
            for kw in _POOL:
                if kw in combined:
                    score -= 5
            if score > best_score:
                best_score = score
                best_entity = s["entity_id"]

        if best_entity and best_score >= 0:
            _LOGGING.info(f"Auto-detected outdoor temp: {best_entity} (score {best_score})")
            return best_entity
        _LOGGING.info("No outdoor temp entity auto-detected")
        return None

    def validate_outdoor_temp_entity(self, configured_entity, all_states=None):
        """
        Compare the configured outdoor temp entity against the top-scored candidates
        and against sensor.tcx_air_temperature (equipment enclosure).

        Returns a list of dicts sorted by score descending, each with:
          entity_id, friendly_name, value_f, score, delta_from_configured
        """
        if all_states is None:
            all_states = self.get_all_states()

        _OUTDOOR = ["openweathermap_temperature", "outdoor", "outside", "exterior",
                    "ambient", "openweathermap", "darksky", "met_no", "pirateweather",
                    "accuweather", "weather", "ecobee_outdoor", "nest_outdoor"]
        _INDOOR  = ["indoor", "inside", "interior", "room", "bedroom", "living",
                    "kitchen", "bathroom", "basement", "garage", "attic", "crawl",
                    "inverter", "processor", "mcu", "pcb", "handle", "extruder",
                    "bed_temperature", "battery_module", "driver_temperature",
                    "passenger_temperature"]
        _POOL    = ["pool", "water", "tcx", "spa", "hot_tub"]

        # Build a lookup: entity_id → float state in °F
        state_map = {}
        for s in all_states:
            try:
                raw_val = float(s.get("state", ""))
            except (ValueError, TypeError):
                continue
            unit = s.get("attributes", {}).get("unit_of_measurement", "")
            val_f = round(raw_val * 9 / 5 + 32, 1) if unit == "°C" else raw_val
            state_map[s["entity_id"]] = val_f

        sensors = self.get_temperature_sensors(all_states)
        candidates = []
        for s in sensors:
            combined = (s["entity_id"] + " " + s["friendly_name"]).lower()
            score = 0
            for kw in _OUTDOOR:
                if kw in combined:
                    score += 3
            for kw in _INDOOR:
                if kw in combined:
                    score -= 4
            for kw in _POOL:
                if kw in combined:
                    score -= 5
            if score < -2:          # skip heavily penalised sensors
                continue
            val_f = state_map.get(s["entity_id"])
            if val_f is None:
                continue
            candidates.append({
                "entity_id": s["entity_id"],
                "friendly_name": s["friendly_name"],
                "value_f": val_f,
                "score": score,
                "delta_from_configured": None,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        candidates = candidates[:8]   # keep top 8 for comparison

        # Resolve configured entity value
        configured_val = state_map.get(configured_entity)

        for c in candidates:
            if configured_val is not None:
                c["delta_from_configured"] = round(c["value_f"] - configured_val, 1)

        # Pull TCX enclosure air for context
        tcx_air = state_map.get("sensor.tcx_air_temperature")

        # Log summary
        _LOGGING.info(
            f"Outdoor temp validation — configured: {configured_entity} = "
            f"{configured_val}°F  |  TCX enclosure air = {tcx_air}°F"
        )
        for c in candidates[:5]:
            marker = " ← configured" if c["entity_id"] == configured_entity else ""
            delta_str = (f"  Δ{c['delta_from_configured']:+.1f}°F vs configured"
                         if c["delta_from_configured"] is not None else "")
            _LOGGING.info(
                f"  [{c['score']:+d}] {c['entity_id']} = {c['value_f']}°F"
                f"{delta_str}{marker}"
            )

        # Warn if configured entity is far off the top candidate
        if candidates and configured_val is not None:
            top = candidates[0]
            if top["entity_id"] != configured_entity and top["value_f"] is not None:
                gap = abs(top["value_f"] - configured_val)
                if gap > 15:
                    _LOGGING.warning(
                        f"Outdoor temp entity {configured_entity} ({configured_val}°F) "
                        f"is {gap:.0f}°F away from top candidate "
                        f"{top['entity_id']} ({top['value_f']}°F) — "
                        f"consider switching in the dashboard"
                    )

        return {
            "configured_entity": configured_entity,
            "configured_value_f": configured_val,
            "tcx_air_f": tcx_air,
            "candidates": candidates,
        }

    def find_chemistry_entities(self, all_states=None):
        """
        Scan HA for pool chemistry sensors.
        Prefers pump-gated mean readings over raw readings.
        Returns: {param: {entity_id, friendly_name, state, unit} | None}
        """
        if all_states is None:
            all_states = self.get_all_states()

        # Keywords that identify each parameter — order matters: first match wins per entity
        _PARAM_KEYWORDS = {
            "ph":       ["ph"],
            "orp":      ["orp", "oxidation_reduction", "redox"],
            "salinity": ["salin", "salt_level"],
            "fc":       ["free_chlorine", "chlorine"],
        }
        # These in entity_id/name disqualify a match for any param
        _EXCLUDE = ["battery", "signal", "rssi", "voltage", "humidity", "pressure",
                    "energy", "power", "current", "bill", "daily", "weekly", "monthly",
                    "yearly", "adjustment", "target", "setpoint",
                    "iphone", "android", "phone", "mobile",   # "iPhone" contains "ph"
                    "swc_level", "swc_production"]             # SWC % ≠ FC ppm

        # Prefer gated_mean > mean > pump_gated > raw (scored by suffix)
        def _quality_score(entity_id):
            eid = entity_id.lower()
            if "gated_mean" in eid:
                return 3
            if "_mean" in eid:
                return 2
            if "pump_gated" in eid or "gated" in eid:
                return 1
            # Boost entities whose name explicitly says "free_chlorine"
            if "free_chlorine" in eid:
                return 1
            return 0

        # Collect all candidates per param, then pick highest quality
        candidates = {k: [] for k in _PARAM_KEYWORDS}

        for s in all_states:
            attrs = s.get("attributes", {})
            entity_id = s["entity_id"]
            eid_lower = entity_id.lower()
            friendly = attrs.get("friendly_name", "").lower()
            combined = eid_lower + " " + friendly
            state_raw = s.get("state", "")

            try:
                float(state_raw)
            except (ValueError, TypeError):
                continue

            if any(kw in combined for kw in _EXCLUDE):
                continue

            for param, keywords in _PARAM_KEYWORDS.items():
                if any(kw in combined for kw in keywords):
                    candidates[param].append({
                        "entity_id": entity_id,
                        "friendly_name": attrs.get("friendly_name", entity_id),
                        "state": state_raw,
                        "unit": attrs.get("unit_of_measurement", ""),
                        "_quality": _quality_score(entity_id),
                    })

        results = {}
        for param, cands in candidates.items():
            if not cands:
                results[param] = None
                continue
            best = max(cands, key=lambda x: x["_quality"])
            best.pop("_quality")
            results[param] = best
            _LOGGING.info(f"Chemistry entity [{param}]: {best['entity_id']} = {best['state']} {best['unit']}")

        return results
