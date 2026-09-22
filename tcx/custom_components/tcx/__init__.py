"""The Jandy TCX integration.

Talks to the companion "Jandy TCX Client" Home Assistant add-on's REST API
(GET /status, POST /statecontrol) to provide switch/light/number entities for
controls the add-on itself only exposes as read-only sensors.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import TCXClient, TCXDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.LIGHT, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Jandy TCX from a config entry."""
    session = async_get_clientsession(hass)
    client = TCXClient(session, entry.data[CONF_HOST], entry.data[CONF_PORT])
    coordinator = TCXDataUpdateCoordinator(hass, client)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
