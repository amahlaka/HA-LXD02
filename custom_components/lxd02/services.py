"""The lxd02.print and lxd02.feed actions, for scripts, automations and other integrations."""
from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ALIGNS,
    ATTR_ALIGN,
    ATTR_COPIES,
    ATTR_DEVICE_ID,
    ATTR_ENERGY,
    ATTR_FEED,
    ATTR_ICON,
    ATTR_IMAGE,
    ATTR_LENGTH,
    ATTR_MARKDOWN,
    ATTR_QR,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_TITLE,
    DEFAULT_ALIGN,
    DEFAULT_SIZE,
    DOMAIN,
    SERVICE_FEED,
    SERVICE_PRINT,
    SIZES,
)
from .manager import ReceiptContent
from .protocol import AUTO_FEED_MM, ENERGY_MAX, ENERGY_MIN

if TYPE_CHECKING:
    from .manager import PrinterManager

# Empty values count as "not set", so scripts can pass optional fields through.
PRINT_SCHEMA = vol.Schema({
    vol.Optional(ATTR_DEVICE_ID): cv.string,
    vol.Optional(ATTR_TITLE, default=""): vol.Any(None, cv.string),
    vol.Optional(ATTR_TEXT, default=""): vol.Any(None, cv.string),
    vol.Optional(ATTR_QR, default=""): vol.Any(None, cv.string),
    vol.Optional(ATTR_ICON, default=""): vol.Any(None, "", cv.icon),
    vol.Optional(ATTR_IMAGE, default=""): vol.Any(None, cv.string),
    vol.Optional(ATTR_SIZE, default=DEFAULT_SIZE): vol.In(SIZES),
    vol.Optional(ATTR_ALIGN, default=DEFAULT_ALIGN): vol.In(ALIGNS),
    vol.Optional(ATTR_MARKDOWN, default=True): cv.boolean,
    vol.Optional(ATTR_COPIES, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
    vol.Optional(ATTR_ENERGY): vol.All(vol.Coerce(int), vol.Range(min=ENERGY_MIN, max=ENERGY_MAX)),
    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
})

FEED_SCHEMA = vol.Schema({
    vol.Optional(ATTR_DEVICE_ID): cv.string,
    # The printer feeds AUTO_FEED_MM by itself after every job, so less isn't possible.
    vol.Optional(ATTR_LENGTH, default=20): vol.All(vol.Coerce(float), vol.Range(min=AUTO_FEED_MM, max=200)),
})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def print_receipt(call: ServiceCall) -> None:
        manager = async_get_manager(hass, call.data.get(ATTR_DEVICE_ID))
        content = ReceiptContent(
            title=call.data[ATTR_TITLE] or "", text=call.data[ATTR_TEXT] or "",
            qr=call.data[ATTR_QR] or "", icon=call.data[ATTR_ICON] or "",
            image=call.data[ATTR_IMAGE] or "", size=call.data[ATTR_SIZE],
            align=call.data[ATTR_ALIGN], markdown=call.data[ATTR_MARKDOWN])
        await manager.async_print(content, copies=call.data[ATTR_COPIES],
                                  energy=call.data.get(ATTR_ENERGY),
                                  feed_mm=call.data.get(ATTR_FEED))

    async def feed(call: ServiceCall) -> None:
        manager = async_get_manager(hass, call.data.get(ATTR_DEVICE_ID))
        await manager.async_feed(call.data[ATTR_LENGTH])

    hass.services.async_register(DOMAIN, SERVICE_PRINT, print_receipt, schema=PRINT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FEED, feed, schema=FEED_SCHEMA)


@callback
def async_get_manager(hass: HomeAssistant, device_id: str | None) -> PrinterManager:
    """The printer for a device ID, or the only printer when none is given."""
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise ServiceValidationError(f"Unknown device {device_id}")
        entries = [e for e in entries if e.entry_id in device.config_entries]
    if not entries:
        raise ServiceValidationError("No LX-D02 printer is set up" if not device_id
                                     else "That device is not a loaded LX-D02 printer")
    if len(entries) > 1:
        raise ServiceValidationError("Several printers are set up; pass device_id")
    return entries[0].runtime_data
