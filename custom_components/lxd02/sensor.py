"""Sensors: status, battery, receipts printed, paper used, last printed."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LXD02ConfigEntry
from .const import STATUS_ERROR, STATUS_IDLE, STATUS_PRINTING
from .entity import LXD02Entity, LXD02LiveEntity
from .manager import PrinterManager


@dataclass(frozen=True, kw_only=True)
class LXD02SensorDescription(SensorEntityDescription):
    value: Callable[[PrinterManager], Any]
    live: bool = False


SENSORS = [
    LXD02SensorDescription(
        key="status", device_class=SensorDeviceClass.ENUM,
        options=[STATUS_IDLE, STATUS_PRINTING, STATUS_ERROR],
        value=lambda m: m.status, live=True),
    LXD02SensorDescription(
        key="battery", device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE,
        value=lambda m: m.printer_status.battery if m.printer_status else None),
    LXD02SensorDescription(
        key="receipts_printed", state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="receipts", value=lambda m: m.receipts_printed),
    LXD02SensorDescription(
        key="paper_used", device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.METERS, suggested_display_precision=2,
        value=lambda m: round(m.paper_used_mm / 1000, 3)),
    LXD02SensorDescription(
        key="last_printed", device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda m: m.last_printed),
]


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities(
        (LXD02LiveSensor if d.live else LXD02Sensor)(manager, d) for d in SENSORS)


class LXD02Sensor(LXD02Entity, SensorEntity):
    entity_description: LXD02SensorDescription

    def __init__(self, manager: PrinterManager, description: LXD02SensorDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.manager)


class LXD02LiveSensor(LXD02LiveEntity, LXD02Sensor):
    """Status: unavailable while the printer is off or held by the phone app."""

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {"last_error": self.manager.last_error} if self.manager.last_error else None
