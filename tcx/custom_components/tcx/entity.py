"""Shared base entity for Jandy TCX platforms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TCXDataUpdateCoordinator


class TCXEntity(CoordinatorEntity[TCXDataUpdateCoordinator]):
    """Base entity tying a TCX control to the shared status coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TCXDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Jandy TCX Pool Controller",
            manufacturer="Jandy / Zodiac",
            model="TCX",
        )
