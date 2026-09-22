from __future__ import annotations


def should_skip_publish(cached: str | None, desired: str, ha_state: str | None) -> bool:
    """Skip only when HA already has the same value we last published."""
    if cached != desired:
        return False
    return ha_state not in (None, "unknown", "unavailable") and ha_state == desired
