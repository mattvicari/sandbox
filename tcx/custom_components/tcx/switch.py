"""Switch platform for Jandy TCX (pump and heater on/off).

Command payloads mirror control_pump()/control_heater() in the add-on's
jandy/resources/index.py.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TCXDataUpdateCoordinator
from .entity import TCXEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TCXDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TCXPumpSwitch(coordinator, entry),
            TCXHeaterSwitch(coordinator, entry),
        ]
    )


class TCXPumpSwitch(TCXEntity, SwitchEntity):
    """Pool pump/filter on-off switch."""

    _attr_icon = "mdi:pump"

    def __init__(self, coordinator: TCXDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pump", "Pump")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("system") == "ON"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_send_command("filtration", {"pool": {"st": 1}})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_send_command("filtration", {"pool": {"st": 0}})
        await self.coordinator.async_request_refresh()


class TCXHeaterSwitch(TCXEntity, SwitchEntity):
    """Heater enable switch."""

    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: TCXDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "heater", "Heater")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("heaterEnabled") == "ON"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_send_command(
            "TCX", {"TspBdy0": {"heatEnabled": 1}}
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_send_command(
            "TCX", {"TspBdy0": {"heatEnabled": 0}}
        )
        await self.coordinator.async_request_refresh()
