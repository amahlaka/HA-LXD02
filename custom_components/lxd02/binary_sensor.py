"""Binary sensors: in range, paper out, charging, overheated (as of the last connection)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LXD02ConfigEntry
from .entity import LXD02Entity
from .manager import PrinterManager
from .protocol import Status


@dataclass(frozen=True, kw_only=True)
class StatusBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[Status], bool]


STATUS_SENSORS = [
    StatusBinaryDescription(key="paper_out", device_class=BinarySensorDeviceClass.PROBLEM,
                            icon="mdi:paper-roll-outline", value=lambda s: s.no_paper),
    StatusBinaryDescription(key="charging", device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
                            value=lambda s: s.charging),
    StatusBinaryDescription(key="overheated", device_class=BinarySensorDeviceClass.HEAT,
                            entity_category=EntityCategory.DIAGNOSTIC, value=lambda s: s.overheated),
]


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities([InRangeSensor(manager),
                        *(StatusBinarySensor(manager, d) for d in STATUS_SENSORS)])


class InRangeSensor(LXD02Entity, BinarySensorEntity):
    """On while the printer advertises: switched on and free for Home Assistant to use."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "in_range")

    @property
    def is_on(self) -> bool:
        return self.manager.available


class StatusBinarySensor(LXD02Entity, BinarySensorEntity):
    """One flag from the printer's status report, as of the last connection."""

    entity_description: StatusBinaryDescription

    def __init__(self, manager: PrinterManager, description: StatusBinaryDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        status = self.manager.printer_status
        return self.entity_description.value(status) if status else None
