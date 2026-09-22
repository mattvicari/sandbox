"""Number platform for Jandy TCX (pump RPM, heater setpoint, SWC level).

Command payloads mirror control_pump_speed()/control_setpoint()/control_swc()
in the add-on's jandy/resources/index.py, including the setpoint's
Fahrenheit -> tenths-of-Celsius conversion.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    HEATER_SETPOINT_MAX_F,
    HEATER_SETPOINT_MIN_F,
    PUMP_RPM_MAX,
    PUMP_RPM_MIN,
    PUMP_RPM_STEP,
)
from .coordinator import TCXDataUpdateCoordinator
from .entity import TCXEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TCXDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TCXPumpRpmNumber(coordinator, entry),
            TCXHeaterSetpointNumber(coordinator, entry),
            TCXSwcLevelNumber(coordinator, entry),
        ]
    )


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TCXPumpRpmNumber(TCXEntity, NumberEntity):
    """Variable-speed pump RPM."""

    _attr_icon = "mdi:speedometer"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = PUMP_RPM_MIN
    _attr_native_max_value = PUMP_RPM_MAX
    _attr_native_step = PUMP_RPM_STEP
    _attr_native_unit_of_measurement = "RPM"

    def __init__(self, coordinator: TCXDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pump_rpm", "Pump Speed")

    @property
    def native_value(self) -> float | None:
        return _as_float(self.coordinator.data.get("pumpRpm"))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_send_command(
            "filtration", {"filt0": {"manSpd": int(value)}}
        )
        await self.coordinator.async_request_refresh()


class TCXHeaterSetpointNumber(TCXEntity, NumberEntity):
    """Heater water temperature setpoint, in Fahrenheit."""

    _attr_icon = "mdi:thermometer"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = HEATER_SETPOINT_MIN_F
    _attr_native_max_value = HEATER_SETPOINT_MAX_F
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(self, coordinator: TCXDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "heater_setpoint", "Heater Setpoint")

    @property
    def native_value(self) -> float | None:
        return _as_float(self.coordinator.data.get("heaterSetpoint"))

    async def async_set_native_value(self, value: float) -> None:
        # Same conversion as control_setpoint(): °F -> tenths of °C.
        raw = round((value - 32) * 5 / 9 * 10)
        await self.coordinator.client.async_send_command(
            "TCX", {"TspBdy0": {"waterTempSet": raw}}
        )
        await self.coordinator.async_request_refresh()


class TCXSwcLevelNumber(TCXEntity, NumberEntity):
    """Salt water chlorinator output level, in percent."""

    _attr_icon = "mdi:water-percent"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: TCXDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "swc_level", "Chlorinator Level")

    @property
    def native_value(self) -> float | None:
        # system_info["swc"] is a string like "45%".
        raw = self.coordinator.data.get("swc")
        if isinstance(raw, str):
            raw = raw.rstrip("%")
        return _as_float(raw)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_send_command(
            "swc", {"swc0": {"stdPoolPcnt": int(value)}}
        )
        await self.coordinator.async_request_refresh()
