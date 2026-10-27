"""Buttons: print the UI form, feed paper, refresh printer state."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LXD02ConfigEntry
from .entity import LXD02LiveEntity
from .manager import PrinterManager

FEED_BUTTON_MM = 20


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager = entry.runtime_data
    async_add_entities([PrintButton(manager), FeedButton(manager), RefreshButton(manager)])


class PrintButton(LXD02LiveEntity, ButtonEntity):
    """Print whatever is in the receipt form."""

    _attr_icon = "mdi:printer"

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "print")

    async def async_press(self) -> None:
        await self.manager.async_print_form()


class FeedButton(LXD02LiveEntity, ButtonEntity):
    """Advance 20 mm of blank paper."""

    _attr_icon = "mdi:arrow-down-bold-box-outline"

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "feed")

    async def async_press(self) -> None:
        await self.manager.async_feed(FEED_BUTTON_MM)


class RefreshButton(LXD02LiveEntity, ButtonEntity):
    """Connect briefly to update battery, paper and charging state."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "refresh")

    async def async_press(self) -> None:
        await self.manager.async_refresh()
