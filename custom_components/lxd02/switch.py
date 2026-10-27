"""Switch: stay connected to the printer for live battery, paper and charging status."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import LXD02ConfigEntry
from .entity import LXD02Entity
from .manager import PrinterManager


async def async_setup_entry(hass: HomeAssistant, entry: LXD02ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([StayConnectedSwitch(entry.runtime_data)])


class StayConnectedSwitch(LXD02Entity, SwitchEntity, RestoreEntity):
    """On: hold the Bluetooth connection, so status is live and prints start
    faster, but the phone app can't reach the printer. Off: connect per job."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, manager: PrinterManager) -> None:
        super().__init__(manager, "stay_connected")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state == "on":
            await self.manager.async_set_stay_connected(True)

    @property
    def is_on(self) -> bool:
        return self.manager.stay_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"connected": self.manager.connected}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.manager.async_set_stay_connected(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.manager.async_set_stay_connected(False)
