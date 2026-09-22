"""
Pool water chemistry recommendation engine.

All dose amounts are per 10,000 gallons; scaled to actual pool volume.
Targets are for a salt-water chlorinated pool.
"""

TARGETS = {
    "fc":        {"low": 1.0,  "high": 3.0,  "unit": "ppm"},
    "ph":        {"low": 7.4,  "high": 7.6,  "unit": ""},
    "ta":        {"low": 80,   "high": 120,  "unit": "ppm"},
    "ch":        {"low": 200,  "high": 400,  "unit": "ppm"},
    "cya":       {"low": 70,   "high": 80,   "unit": "ppm"},  # SWC target
    "salinity":  {"low": 2700, "high": 3400, "unit": "ppm"},
}

# Raise amounts per 10,000 gal to move by 1 unit (oz unless noted)
_RAISE = {
    "ph_soda_ash":      6.0,   # oz soda ash raises pH ~0.2
    "ta_bicarb":        21.0,  # oz sodium bicarb raises TA 10 ppm  → 2.1 oz/ppm
    "ch_calcium_chloride": 12.0,  # oz CaCl2 raises CH 10 ppm
    "cya_cyanuric":     13.0,  # oz CYA raises CYA 10 ppm
    "salt_nacl_lbs":    0.8,   # lbs pool salt raises salinity 100 ppm
}

# Lower amounts per 10,000 gal
_LOWER = {
    "ph_acid_oz":       10.0,   # oz muriatic acid lowers pH ~0.2
    "ta_acid_oz":       10.0,   # oz muriatic acid lowers TA 10 ppm
}


def _scale(amount_per_10k, pool_volume):
    return round(amount_per_10k * pool_volume / 10000, 1)


def recommend(readings: dict, pool_volume: int) -> list:
    """
    Given a dict of {param: value} and pool volume in gallons,
    return a list of recommendation dicts:
      {param, current, target_low, target_high, unit, status, action, chemical, amount, amount_unit}
    """
    results = []

    fc = readings.get("fc")
    ph = readings.get("ph")
    ta = readings.get("ta")
    ch = readings.get("ch")
    cya = readings.get("cya")
    salinity_ppm = readings.get("salinity")

    # Free Chlorine
    if fc is not None:
        t = TARGETS["fc"]
        if fc < t["low"]:
            deficit = t["low"] - fc
            action = f"Shock or boost SWC output. Target {t['low']}–{t['high']} ppm."
            results.append({
                "param": "Free Chlorine", "current": fc,
                "target": f"{t['low']}–{t['high']} ppm", "status": "LOW",
                "action": action, "chemical": "Increase SWC / add liquid chlorine",
                "amount": None, "amount_unit": None
            })
        elif fc > t["high"]:
            results.append({
                "param": "Free Chlorine", "current": fc,
                "target": f"{t['low']}–{t['high']} ppm", "status": "HIGH",
                "action": "Reduce SWC output or allow sun to burn off excess.",
                "chemical": None, "amount": None, "amount_unit": None
            })
        else:
            results.append(_ok("Free Chlorine", fc, f"{t['low']}–{t['high']} ppm"))

    # pH
    if ph is not None:
        t = TARGETS["ph"]
        if ph < t["low"]:
            delta = t["low"] - ph
            doses = round(delta / 0.2)
            oz = _scale(_RAISE["ph_soda_ash"], pool_volume) * doses
            results.append({
                "param": "pH", "current": ph,
                "target": f"{t['low']}–{t['high']}", "status": "LOW",
                "action": f"Add soda ash (sodium carbonate) to raise pH to {t['low']}–{t['high']}.",
                "chemical": "Soda Ash (sodium carbonate)",
                "amount": oz, "amount_unit": "oz"
            })
        elif ph > t["high"]:
            delta = ph - t["high"]
            doses = round(delta / 0.2)
            oz = _scale(_LOWER["ph_acid_oz"], pool_volume) * doses
            results.append({
                "param": "pH", "current": ph,
                "target": f"{t['low']}–{t['high']}", "status": "HIGH",
                "action": f"Add muriatic acid to lower pH to {t['low']}–{t['high']}.",
                "chemical": "Muriatic Acid",
                "amount": oz, "amount_unit": "oz"
            })
        else:
            results.append(_ok("pH", ph, f"{t['low']}–{t['high']}"))

    # Total Alkalinity
    if ta is not None:
        t = TARGETS["ta"]
        if ta < t["low"]:
            ppm_needed = t["low"] - ta
            oz = _scale(_RAISE["ta_bicarb"], pool_volume) * ppm_needed / 10
            results.append({
                "param": "Total Alkalinity", "current": f"{ta} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "LOW",
                "action": "Add sodium bicarbonate (baking soda) to raise alkalinity.",
                "chemical": "Sodium Bicarbonate",
                "amount": round(oz / 16, 2), "amount_unit": "lbs"
            })
        elif ta > t["high"]:
            ppm_over = ta - t["high"]
            oz = _scale(_LOWER["ta_acid_oz"], pool_volume) * ppm_over / 10
            results.append({
                "param": "Total Alkalinity", "current": f"{ta} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "HIGH",
                "action": "Add muriatic acid with pump off to lower alkalinity.",
                "chemical": "Muriatic Acid",
                "amount": oz, "amount_unit": "oz"
            })
        else:
            results.append(_ok("Total Alkalinity", f"{ta} ppm", f"{t['low']}–{t['high']} ppm"))

    # Calcium Hardness
    if ch is not None:
        t = TARGETS["ch"]
        if ch < t["low"]:
            ppm_needed = t["low"] - ch
            oz = _scale(_RAISE["ch_calcium_chloride"], pool_volume) * ppm_needed / 10
            results.append({
                "param": "Calcium Hardness", "current": f"{ch} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "LOW",
                "action": "Add calcium chloride to raise hardness.",
                "chemical": "Calcium Chloride",
                "amount": round(oz / 16, 2), "amount_unit": "lbs"
            })
        elif ch > t["high"]:
            results.append({
                "param": "Calcium Hardness", "current": f"{ch} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "HIGH",
                "action": "Partially drain and refill with fresh water to dilute.",
                "chemical": None, "amount": None, "amount_unit": None
            })
        else:
            results.append(_ok("Calcium Hardness", f"{ch} ppm", f"{t['low']}–{t['high']} ppm"))

    # Cyanuric Acid (stabilizer)
    if cya is not None:
        t = TARGETS["cya"]
        if cya < t["low"]:
            ppm_needed = t["low"] - cya
            oz = _scale(_RAISE["cya_cyanuric"], pool_volume) * ppm_needed / 10
            results.append({
                "param": "Cyanuric Acid (Stabilizer)", "current": f"{cya} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "LOW",
                "action": "Add cyanuric acid to protect chlorine from UV degradation.",
                "chemical": "Cyanuric Acid",
                "amount": round(oz / 16, 2), "amount_unit": "lbs"
            })
        elif cya > t["high"]:
            results.append({
                "param": "Cyanuric Acid (Stabilizer)", "current": f"{cya} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "HIGH",
                "action": "Partially drain and refill with fresh water to dilute.",
                "chemical": None, "amount": None, "amount_unit": None
            })
        else:
            results.append(_ok("Cyanuric Acid", f"{cya} ppm", f"{t['low']}–{t['high']} ppm"))

    # Salinity (convert g/L to ppm: 1 g/L = 1000 ppm)
    if salinity_ppm is not None:
        t = TARGETS["salinity"]
        if salinity_ppm < t["low"]:
            ppm_needed = t["low"] - salinity_ppm
            lbs = _scale(_RAISE["salt_nacl_lbs"], pool_volume) * ppm_needed / 100
            results.append({
                "param": "Salinity", "current": f"{salinity_ppm} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "LOW",
                "action": "Add pool-grade salt (NaCl) to raise salinity.",
                "chemical": "Pool Salt (NaCl)",
                "amount": round(lbs, 1), "amount_unit": "lbs"
            })
        elif salinity_ppm > t["high"]:
            results.append({
                "param": "Salinity", "current": f"{salinity_ppm} ppm",
                "target": f"{t['low']}–{t['high']} ppm", "status": "HIGH",
                "action": "Partially drain and refill with fresh water to dilute.",
                "chemical": None, "amount": None, "amount_unit": None
            })
        else:
            results.append(_ok("Salinity", f"{salinity_ppm} ppm", f"{t['low']}–{t['high']} ppm"))

    return results


def _ok(param, current, target):
    return {
        "param": param, "current": current, "target": target,
        "status": "OK", "action": "In range.", "chemical": None,
        "amount": None, "amount_unit": None
    }
