"""Notify entity: notify.send_message prints the message as a receipt."""
from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LXD02ConfigEntry
from .entity import LXD02LiveEntity
from .manager import PrinterManager, ReceiptContent


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([ReceiptNotify(entry.runtime_data)])


class ReceiptNotify(LXD02LiveEntity, NotifyEntity):
    """Title becomes the heading, message the body text."""

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "receipt")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        await self.manager.async_print(ReceiptContent(title=title or "", text=message))
