"""Bluetooth LE connection to an LX-D02, on Home Assistant's Bluetooth stack.

The protocol itself is in protocol.py, shared with the standalone CLI.
"""
from __future__ import annotations

import logging

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .bluez import async_prefer_le
from .protocol import LXD02, PrinterError

_LOGGER = logging.getLogger(__name__)

__all__ = ["LXD02Connection", "PrinterError"]


class LXD02Connection(LXD02):
    """One unlocked connection to the printer; use as an async context manager."""

    def __init__(self, ble_device: BLEDevice) -> None:
        super().__init__(None)
        self.ble_device = ble_device

    async def __aenter__(self) -> LXD02Connection:
        await async_prefer_le(self.ble_device)
        self.client = await establish_connection(
            BleakClientWithServiceCache, self.ble_device,
            self.ble_device.name or self.ble_device.address, max_attempts=3)
        try:
            await self.start()
        except BaseException:
            await self.client.disconnect()
            raise
        _LOGGER.debug("connected to %s (MAC %s)", self.ble_device.address, self.mac_address)
        return self

    async def __aexit__(self, *exc) -> None:
        if self.client and self.client.is_connected:
            await self.client.disconnect()
