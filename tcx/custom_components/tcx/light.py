"""Light platform for Jandy TCX (pool light on/off plus color programs).

Command payloads mirror control_light()/control_light_color() in the add-on's
jandy/resources/index.py. Namespace is "zig" (not MQTT "zigbee").
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LIGHT_COLOR_NAME_TO_NUMBER, LIGHT_COLORS
from .coordinator import TCXDataUpdateCoordinator
from .entity import TCXEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TCXDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TCXPoolLight(coordinator, entry)])


class TCXPoolLight(TCXEntity, LightEntity):
    """Pool light with the 12 Jandy SAm iColor programs as effects."""

    _attr_icon = "mdi:pool"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(LIGHT_COLORS.values())

    def __init__(self, coordinator: TCXDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pool_light", "Pool Light")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("light") == "ON"

    @property
    def effect(self) -> str | None:
        return self.coordinator.data.get("lightColorName") or None

    async def async_turn_on(self, **kwargs: Any) -> None:
        auxz0: dict[str, Any] = {"st": 1}
        effect = kwargs.get("effect")
        if effect and effect in LIGHT_COLOR_NAME_TO_NUMBER:
            auxz0["cmdClr"] = LIGHT_COLOR_NAME_TO_NUMBER[effect]
        await self.coordinator.client.async_send_command("zig", {"auxz0": auxz0})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_send_command("zig", {"auxz0": {"st": 0}})
        await self.coordinator.async_request_refresh()
