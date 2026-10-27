"""State and print queue for one LX-D02, shared by its entities and actions."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_ALIGN,
    DEFAULT_ENERGY,
    DEFAULT_FEED,
    DEFAULT_SIZE,
    DOMAIN,
    MAX_TEXT_LENGTH,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_PRINTING,
)
from .printer import LXD02Connection, PrinterError
from .protocol import AUTO_FEED_MM, DOTS_PER_MM, Status
from .receipt import render_receipt

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
KEEP_CHECK_INTERVAL = 5  # s between checks that a held connection is still up
RECONNECT_INTERVAL = 15  # s between attempts to get the connection back


@dataclass
class ReceiptContent:
    """What goes on a receipt; empty fields are left off."""

    title: str = ""
    text: str = ""
    qr: str = ""
    icon: str = ""
    image: str = ""  # path of a picture on the Home Assistant host
    size: str = DEFAULT_SIZE
    align: str = DEFAULT_ALIGN
    markdown: bool = True  # format the text as Markdown

    def is_empty(self) -> bool:
        return not (self.title or self.text or self.qr or self.icon or self.image)


class PrinterManager:
    """Owns the Bluetooth presence, settings, UI form and print queue of one printer."""

    def __init__(self, hass: HomeAssistant, entry_id: str, address: str, name: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.address = address
        self.name = name
        self.lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{address}")

        self.present = False
        self.status = STATUS_IDLE
        self.last_error: str | None = None
        # The printer only reports its state while connected, so this is
        # live in stay-connected mode and otherwise as of the last connection.
        self.printer_status: Status | None = None
        self.stay_connected = False
        self._conn: LXD02Connection | None = None  # held in stay-connected mode
        self._keeper: asyncio.Task | None = None
        self.receipts_printed = 0
        self.paper_used_mm = 0.0
        self.last_printed: datetime | None = None

        # Settings (config entities) and the UI print form (input entities).
        self.energy = DEFAULT_ENERGY
        self.feed_mm = DEFAULT_FEED
        self.form = ReceiptContent()
        self.form_copies = 1
        # Bumped whenever something that changes the receipt preview changes.
        self.preview_version = 0

    @callback
    def async_form_changed(self) -> None:
        self.preview_version += 1
        self.async_update_listeners()

    # --- listeners -----------------------------------------------------

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def async_update_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    @property
    def connected(self) -> bool:
        """True while stay-connected mode holds a live connection."""
        return self._conn is not None and self._conn.is_connected

    @property
    def available(self) -> bool:
        # While connected to us the printer stops advertising.
        return self.present or self.connected or self.status == STATUS_PRINTING

    # --- startup / presence ----------------------------------------------

    async def async_load(self) -> None:
        if data := await self._store.async_load():
            self.receipts_printed = data.get("receipts_printed", 0)
            self.paper_used_mm = data.get("paper_used_mm", 0.0)
            if last := data.get("last_printed"):
                self.last_printed = dt_util.parse_datetime(last)

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Track whether the printer is advertising (on and not busy with the phone app)."""
        self.present = bluetooth.async_address_present(self.hass, self.address, connectable=True)

        @callback
        def _seen(service_info, change) -> None:
            if not self.present:
                self.present = True
                self.async_update_listeners()

        @callback
        def _gone(service_info) -> None:
            self.present = False
            self.async_update_listeners()

        unsubs = [
            bluetooth.async_register_callback(
                self.hass, _seen,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.PASSIVE),
            bluetooth.async_track_unavailable(self.hass, _gone, self.address, connectable=True),
        ]

        @callback
        def _stop() -> None:
            for unsub in unsubs:
                unsub()

        return _stop

    # --- stay-connected mode ------------------------------------------------

    async def async_set_stay_connected(self, on: bool) -> None:
        """Hold the connection for live status, or go back to connecting per job."""
        self.stay_connected = on
        if on and self._keeper is None:
            self._keeper = self.hass.async_create_background_task(
                self._keep_connected(), f"{DOMAIN} {self.address} stay connected")
        elif not on and self._keeper is not None:
            self._keeper.cancel()
            self._keeper = None
            async with self.lock:
                await self._disconnect()
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        if self._keeper is not None:
            self._keeper.cancel()
            self._keeper = None
        await self._disconnect()

    async def _keep_connected(self) -> None:
        was_connected = False
        while True:
            if not self.connected:
                if was_connected:
                    _LOGGER.debug("lost the connection to %s", self.address)
                    await self._disconnect()
                await self._try_connect()
            was_connected = self.connected
            await asyncio.sleep(KEEP_CHECK_INTERVAL if was_connected else RECONNECT_INTERVAL)

    async def _try_connect(self) -> None:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            return  # off, out of range or held by the phone app; try again later
        async with self.lock:
            conn = LXD02Connection(ble_device)
            try:
                await conn.__aenter__()
            except Exception:  # bleak raises a variety of connection errors
                _LOGGER.debug("could not connect to %s", self.address, exc_info=True)
                return
            conn.on_status = self._on_live_status
            self._conn = conn
            if conn.status:
                self.printer_status = conn.status
        _LOGGER.debug("holding the connection to %s", self.address)
        self.async_update_listeners()

    @callback
    def _on_live_status(self, status: Status) -> None:
        self.printer_status = status
        self.async_update_listeners()

    async def _disconnect(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        conn.on_status = None
        try:
            await conn.__aexit__(None, None, None)
        except Exception:  # already gone
            _LOGGER.debug("disconnect failed", exc_info=True)
        self.async_update_listeners()

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {
            "receipts_printed": self.receipts_printed,
            "paper_used_mm": round(self.paper_used_mm, 1),
            "last_printed": self.last_printed.isoformat() if self.last_printed else None,
        }, 5)

    # --- rendering ---------------------------------------------------------

    def _open_picture(self, path: str) -> Image.Image:
        if not self.hass.config.is_allowed_path(path):
            raise ServiceValidationError(
                f"{path} is not in an allowed folder; add its folder to "
                "allowlist_external_dirs in configuration.yaml")
        try:
            with Image.open(Path(path)) as img:
                img.load()
                return img
        except OSError as err:
            raise ServiceValidationError(f"Could not open {path}: {err}") from err

    def _render(self, content: ReceiptContent) -> Image.Image:
        picture = self._open_picture(content.image) if content.image else None
        return render_receipt(title=content.title, text=content.text, qr=content.qr or None,
                              icon=content.icon or None, picture=picture,
                              size=content.size, align=content.align, markdown=content.markdown,
                              load_image=self._open_picture)

    async def async_render(self, content: ReceiptContent) -> Image.Image:
        """Render off the event loop; bad content raises ServiceValidationError."""
        if content.is_empty():
            raise ServiceValidationError(
                "Nothing to print: fill in a title, text, QR code, icon or picture")
        length = len(content.title) + len(content.text) + len(content.qr)
        if length > MAX_TEXT_LENGTH:
            # Several metres of paper; also bounds the work of rendering text
            # that may come from outside (notify messages, automations).
            raise ServiceValidationError(
                f"Too much text to print: {length} characters (at most {MAX_TEXT_LENGTH})")
        try:
            return await self.hass.async_add_executor_job(self._render, content)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def async_preview_png(self) -> bytes:
        """The UI form as a PNG, framed so the paper edges show on screen."""
        def _png() -> bytes:
            try:
                img = self._render(self.form) if not self.form.is_empty() else None
            except (ValueError, ServiceValidationError):
                img = None
            if img is None:
                img = Image.new("L", (384, 96), 255)
            img = ImageOps.expand(img, border=2, fill=160)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        return await self.hass.async_add_executor_job(_png)

    # --- printing ----------------------------------------------------------

    async def async_print(self, content: ReceiptContent, copies: int = 1, energy: int | None = None,
                          feed_mm: float | None = None) -> None:
        image = await self.async_render(content)
        feed = self.feed_mm if feed_mm is None else feed_mm

        async def job(printer: LXD02Connection) -> None:
            for _ in range(copies):
                await printer.print_image(image, energy=energy or self.energy, feed_mm=feed)
                self._count(image.height / DOTS_PER_MM + feed + AUTO_FEED_MM, receipt=True)

        await self._async_session(job)

    async def async_print_form(self) -> None:
        await self.async_print(self.form, self.form_copies)

    async def async_feed(self, length_mm: float) -> None:
        """Advance blank paper; the printer's own AUTO_FEED_MM is included, so it's the minimum."""
        async def job(printer: LXD02Connection) -> None:
            await printer.feed(length_mm)
            self._count(max(length_mm, AUTO_FEED_MM), receipt=False)

        await self._async_session(job)

    async def async_refresh(self) -> None:
        """Connect briefly to read battery, paper and charging state."""
        await self._async_session(None)

    def _count(self, length_mm: float, receipt: bool) -> None:
        if receipt:
            self.receipts_printed += 1
            self.last_printed = dt_util.utcnow()
        self.paper_used_mm += length_mm
        self.async_update_listeners()

    async def _async_session(self, job: Callable[[LXD02Connection], Awaitable[None]] | None) -> None:
        ble_device = None if self.connected else self._ble_device()
        async with self.lock:
            self.status = STATUS_PRINTING
            self.async_update_listeners()
            try:
                if self.connected:
                    await self._run(self._conn, job)
                else:
                    # The held connection may have dropped while we waited for the lock.
                    async with LXD02Connection(ble_device or self._ble_device()) as printer:
                        await self._run(printer, job)
                self.status = STATUS_IDLE
                self.last_error = None
            except PrinterError as err:
                self._fail(str(err))
                raise HomeAssistantError(f"Printing failed: {err}") from err
            except HomeAssistantError as err:
                self._fail(str(err))
                raise
            except Exception as err:  # bleak raises a variety of connection errors
                _LOGGER.debug("printer connection failed", exc_info=True)
                self._fail(f"connection failed: {err}")
                raise HomeAssistantError(f"Could not talk to the printer: {err}") from err
            finally:
                self._save()
                self.async_update_listeners()

    def _ble_device(self):
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            raise HomeAssistantError(
                f"{self.name} is not reachable: it is off (it powers off when idle), "
                "out of Bluetooth range, or connected to the phone app")
        return ble_device

    async def _run(self, printer: LXD02Connection,
                   job: Callable[[LXD02Connection], Awaitable[None]] | None) -> None:
        await self._read_status(printer)
        if job is not None:
            if self.printer_status and self.printer_status.no_paper:
                raise PrinterError("the printer is out of paper")
            await job(printer)
        if printer.status:
            self.printer_status = printer.status

    def _fail(self, message: str) -> None:
        self.status = STATUS_ERROR
        self.last_error = message

    async def _read_status(self, printer: LXD02Connection) -> None:
        try:
            self.printer_status = await printer.wait_status()
        except PrinterError:
            _LOGGER.debug("no status frame from the printer", exc_info=True)
            return
        self.async_update_listeners()
