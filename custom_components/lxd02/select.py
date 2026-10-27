"""Selects for the receipt form: text size and alignment."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import LXD02ConfigEntry
from .const import ALIGNS, SIZES
from .entity import LXD02Entity
from .manager import PrinterManager

FIELDS = {
    # key: (options, icon)
    "size": (SIZES, "mdi:format-size"),
    "align": (ALIGNS, "mdi:format-align-left"),
}


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities(FormSelect(manager, key, options, icon)
                       for key, (options, icon) in FIELDS.items())


class FormSelect(LXD02Entity, SelectEntity, RestoreEntity):
    """Text size or alignment of the receipt form."""

    def __init__(self, manager: PrinterManager, key: str, options: list[str], icon: str) -> None:
        super().__init__(manager, f"form_{key}")
        self._key = key
        self._attr_options = options
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in self.options:
            setattr(self.manager.form, self._key, last.state)
            self.manager.async_form_changed()

    @property
    def current_option(self) -> str:
        return getattr(self.manager.form, self._key)

    async def async_select_option(self, option: str) -> None:
        setattr(self.manager.form, self._key, option)
        self.manager.async_form_changed()
