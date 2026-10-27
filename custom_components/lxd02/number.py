"""Numbers: copies for the form; print darkness and feed after printing."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LXD02ConfigEntry
from .entity import LXD02Entity
from .manager import PrinterManager
from .protocol import ENERGY_MAX, ENERGY_MIN


@dataclass(frozen=True, kw_only=True)
class LXD02NumberDescription(NumberEntityDescription):
    attr: str  # PrinterManager attribute it controls
    cast: type = float


NUMBERS = [
    LXD02NumberDescription(
        key="copies", attr="form_copies", cast=int, icon="mdi:content-copy",
        native_min_value=1, native_max_value=20, native_step=1, mode=NumberMode.BOX),
    LXD02NumberDescription(
        key="energy", attr="energy", cast=int, entity_category=EntityCategory.CONFIG,
        native_min_value=ENERGY_MIN, native_max_value=ENERGY_MAX, native_step=1,
        mode=NumberMode.SLIDER, icon="mdi:brightness-6"),
    LXD02NumberDescription(
        key="feed", attr="feed_mm", entity_category=EntityCategory.CONFIG,
        native_min_value=0, native_max_value=50, native_step=1, mode=NumberMode.BOX,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, icon="mdi:arrow-expand-down"),
]


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities(LXD02Number(manager, d) for d in NUMBERS)


class LXD02Number(LXD02Entity, RestoreNumber):
    entity_description: LXD02NumberDescription

    def __init__(self, manager: PrinterManager, description: LXD02NumberDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._apply(last.native_value)

    @property
    def native_value(self) -> float:
        return getattr(self.manager, self.entity_description.attr)

    async def async_set_native_value(self, value: float) -> None:
        self._apply(value)

    def _apply(self, value: float) -> None:
        setattr(self.manager, self.entity_description.attr, self.entity_description.cast(value))
        self.manager.async_update_listeners()
