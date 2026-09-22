"""
Chemistry resource — two distinct concerns kept strictly separate:

BACKGROUND (WebSocket thread / startup):
  run_chemistry_refresh()
    → reads HA sensors via ha_api.get_state()   [may block]
    → runs recommend()
    → writes results into CONST.chemistry_*
    → publishes sensor.tcx_chemistry_* to HA

WEB ROUTE (gunicorn worker):
  chemistry_page()
    → reads CONST.chemistry_readings / CONST.chemistry_results  [no HTTP, no blocking]
    → renders template

The web route NEVER calls ha_api.get_state() directly.
All blocking HA HTTP calls happen in the background thread only.
"""

import logging
import time

from flask import Blueprint, render_template, request

from jandy import CONST
from jandy.chemistry import recommend

_LOGGER = logging.getLogger()
chemistry_bp = Blueprint("chemistry", __name__)

_CHEM_SENSOR_META = {
    "Free Chlorine":              ("sensor.tcx_chemistry_fc",       "ppm", "TCX Free Chlorine"),
    "pH":                         ("sensor.tcx_chemistry_ph",        "",    "TCX pH"),
    "Total Alkalinity":           ("sensor.tcx_chemistry_ta",       "ppm", "TCX Total Alkalinity"),
    "Calcium Hardness":           ("sensor.tcx_chemistry_ch",       "ppm", "TCX Calcium Hardness"),
    "Cyanuric Acid (Stabilizer)": ("sensor.tcx_chemistry_cya",      "ppm", "TCX Cyanuric Acid"),
    "Salinity":                   ("sensor.tcx_chemistry_salinity", "ppm", "TCX Salinity"),
}

AUTO_REFRESH_INTERVAL = 30 * 60   # seconds between automatic background refreshes
_last_auto_refresh: float = 0


# ── Background helpers (called from WebSocket thread / startup only) ─────────

def _salinity_gl_to_ppm(value):
    try:
        return round(float(value) * 1000)
    except (TypeError, ValueError):
        return None


def _read_ha_chemistry_blocking():
    """
    Read live chemistry values FROM HA. Blocking HTTP calls — must only
    be called from the background/WebSocket thread, never from a web route.
    HA is the source of truth; TCX contributes salinity only.
    """
    readings = {}
    if not CONST.ha_api:
        return readings
    for param, entity in CONST.chemistry_entities.items():
        if not entity:
            continue
        try:
            live = CONST.ha_api.get_state(entity["entity_id"])
            val = float(live)
            readings[param] = val
            _LOGGER.debug(f"Chemistry: {param} = {val} from {entity['entity_id']}")
        except (TypeError, ValueError):
            pass
    # TCX salinity (g/L → ppm) — only chemistry value TCX itself provides
    tcx_sal = _salinity_gl_to_ppm(CONST.system_info.get("salinity_gl"))
    if tcx_sal:
        readings["salinity"] = tcx_sal
        _LOGGER.debug(f"Chemistry: salinity = {tcx_sal} ppm from TCX sensor")
    return readings


def _publish_results_to_ha(results):
    """Publish recommend() results as HA sensors. Blocking — background thread only."""
    if not CONST.ha_api or not results:
        return
    for r in results:
        meta = _CHEM_SENSOR_META.get(r["param"])
        if not meta:
            continue
        entity_id, unit, friendly = meta
        try:
            state_val = float(str(r["current"]).replace(" ppm", "").replace(" g/L", ""))
        except (ValueError, TypeError):
            state_val = r["current"]
        extra = {"status": r["status"], "target": r["target"], "action": r["action"]}
        if r.get("chemical"):
            extra["chemical"] = r["chemical"]
        if r.get("amount") is not None:
            extra["dose"] = f"{r['amount']} {r['amount_unit']}"
        try:
            CONST.ha_api.set_sensor(
                entity_id, state_val,
                unit=unit or None,
                friendly_name=friendly,
                extra_attributes=extra,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to publish {entity_id}: {e}")


def run_chemistry_refresh(force: bool = False):
    """
    Read HA chemistry, compute recommendations, publish to HA, cache in CONST.
    Rate-limited to AUTO_REFRESH_INTERVAL unless force=True.
    Safe to call from WebSocket thread or startup — NOT from gunicorn workers.
    """
    global _last_auto_refresh
    now = time.time()
    if not force and (now - _last_auto_refresh) < AUTO_REFRESH_INTERVAL:
        return

    if not CONST.POOL_VOLUME:
        _LOGGER.debug("Chemistry refresh skipped — pool volume not configured")
        return

    readings = _read_ha_chemistry_blocking()
    if not readings:
        _LOGGER.debug("Chemistry refresh skipped — no HA chemistry entities found")
        return

    results = recommend(readings, CONST.POOL_VOLUME)

    # Cache in CONST so web routes can read without any HTTP calls
    CONST.chemistry_readings = dict(readings)
    CONST.chemistry_results  = results
    CONST.chemistry_last_updated = now

    _publish_results_to_ha(results)
    _last_auto_refresh = now

    out_of_range = [r for r in results if r["status"] != "OK"]
    _LOGGER.info(
        f"Chemistry refresh: {len(results)} params, "
        f"{len(out_of_range)} out of range"
        + (f": {[r['param'] for r in out_of_range]}" if out_of_range else "")
    )
    return results


# ── Web route (gunicorn worker — no blocking calls) ───────────────────────────

@chemistry_bp.route("/chemistry", methods=["GET", "POST"])
def chemistry_page():
    # Pre-fill form from CONST cache — no HTTP calls here
    form = {k: str(round(v, 2)) for k, v in CONST.chemistry_readings.items()}
    results = CONST.chemistry_results or None
    last_updated = CONST.chemistry_last_updated

    if request.method == "POST":
        # Manual override — start from cached HA readings, apply form values
        readings = dict(CONST.chemistry_readings)
        for field in ("fc", "ph", "ta", "ch", "cya", "salinity"):
            raw = request.form.get(field, "").strip()
            if raw:
                try:
                    readings[field] = float(raw)
                    form[field] = raw
                except ValueError:
                    pass
        if readings:
            results = recommend(readings, CONST.POOL_VOLUME)
            # Store manual results in cache but don't publish to HA
            # (manual overrides shouldn't overwrite HA-sourced sensor values)
            CONST.chemistry_results = results
            last_updated = CONST.chemistry_last_updated

    return render_template(
        "chemistry.html",
        pool_volume=CONST.POOL_VOLUME,
        form=form,
        results=results,
        last_updated=last_updated,
        chemistry_entities=CONST.chemistry_entities,
    )
