"""Image: live preview of the receipt form."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import LXD02ConfigEntry
from .entity import LXD02Entity
from .manager import PrinterManager


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([ReceiptPreview(hass, entry.runtime_data)])


class ReceiptPreview(LXD02Entity, ImageEntity):
    """What the Print button would print, at 1 px per printer dot."""

    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, manager: PrinterManager) -> None:
        LXD02Entity.__init__(self, manager, "preview")
        ImageEntity.__init__(self, hass)
        self._version = -1
        self._attr_image_last_updated = dt_util.utcnow()

    def _handle_manager_update(self) -> None:
        if self.manager.preview_version != self._version:
            self._version = self.manager.preview_version
            self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return await self.manager.async_preview_png()
