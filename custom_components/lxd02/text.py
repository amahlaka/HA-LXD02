"""Text inputs for the receipt form: title, text, QR content, icon."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import LXD02ConfigEntry
from .entity import LXD02Entity
from .manager import PrinterManager
from .receipt import mdi_glyph

FIELDS = {
    # key: icon
    "title": "mdi:format-title",
    "text": "mdi:text",
    "qr": "mdi:qrcode",
    "icon": "mdi:emoticon-outline",
}


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities(FormText(manager, key, icon) for key, icon in FIELDS.items())


class FormText(LXD02Entity, TextEntity, RestoreEntity):
    """One field of the receipt form; empty means "leave it off"."""

    _attr_native_min = 0
    _attr_native_max = 255
    _attr_mode = TextMode.TEXT

    def __init__(self, manager: PrinterManager, key: str, icon: str) -> None:
        super().__init__(manager, f"form_{key}")
        self._key = key
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            setattr(self.manager.form, self._key, last.state)
            self.manager.async_form_changed()

    @property
    def native_value(self) -> str:
        return getattr(self.manager.form, self._key)

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        if self._key == "icon" and value:
            value = value if value.startswith("mdi:") else f"mdi:{value}"
            try:
                await self.hass.async_add_executor_job(mdi_glyph, value)
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err
        setattr(self.manager.form, self._key, value)
        self.manager.async_form_changed()
