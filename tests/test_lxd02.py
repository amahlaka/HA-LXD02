"""Tests for the lxd02 receipt printer integration."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.components.image import async_get_image
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.lxd02.protocol import PrinterError, Status

DOMAIN = "lxd02"
ADDRESS = "C0:00:00:00:00:48"
NAME = "LX-D02"
STATUS = bytes.fromhex("5a0257000000000300000040")


class FakeConnection:
    """Stands in for printer.LXD02Connection and records what would be printed."""

    jobs: list = []
    feeds: list = []
    instances: list = []
    fail_with: Exception | None = None
    status = Status.parse(STATUS)

    def __init__(self, ble_device):
        self.is_connected = False
        self.on_status = None
        FakeConnection.instances.append(self)

    async def __aenter__(self):
        if FakeConnection.fail_with:
            raise FakeConnection.fail_with
        self.is_connected = True
        return self

    async def __aexit__(self, *exc):
        self.is_connected = False

    async def wait_status(self):
        return FakeConnection.status

    async def print_image(self, img, **kwargs):
        FakeConnection.jobs.append((img.size, kwargs))

    async def print_raw(self, data, energy=None):
        FakeConnection.feeds.append(len(data))

    async def feed(self, length_mm):
        FakeConnection.feeds.append(length_mm)


@pytest.fixture
def fake_printer(hass: HomeAssistant):
    hass.config.components.add("bluetooth_adapters")
    FakeConnection.jobs, FakeConnection.feeds, FakeConnection.fail_with = [], [], None
    FakeConnection.instances = []
    FakeConnection.status = Status.parse(STATUS)
    bt = "custom_components.lxd02.manager.bluetooth"
    with (
        patch("custom_components.lxd02.manager.LXD02Connection", FakeConnection),
        patch("custom_components.lxd02.manager.KEEP_CHECK_INTERVAL", 0.01),
        patch("custom_components.lxd02.manager.RECONNECT_INTERVAL", 0.01),
        patch(f"{bt}.async_address_present", return_value=True),
        patch(f"{bt}.async_register_callback", return_value=lambda: None),
        patch(f"{bt}.async_track_unavailable", return_value=lambda: None),
        patch(f"{bt}.async_ble_device_from_address", return_value=SimpleNamespace(address=ADDRESS, name=NAME)),
    ):
        yield FakeConnection


@pytest.fixture
async def printer_entry(hass: HomeAssistant, fake_printer) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}, title="LX-D02 0048")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def eid(hass: HomeAssistant, platform: str, key: str) -> str:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}")


def state(hass: HomeAssistant, platform: str, key: str) -> str:
    return hass.states.get(eid(hass, platform, key)).state


async def call(hass: HomeAssistant, domain: str, service: str, data: dict) -> None:
    await hass.services.async_call(domain, service, data, blocking=True)


async def set_text(hass: HomeAssistant, key: str, value: str) -> None:
    await call(hass, "text", "set_value", {"entity_id": eid(hass, "text", key), "value": value})


async def press(hass: HomeAssistant, key: str) -> None:
    await call(hass, "button", "press", {"entity_id": eid(hass, "button", key)})


# --- config flow --------------------------------------------------------------

async def test_user_flow(hass: HomeAssistant, fake_printer) -> None:
    info = SimpleNamespace(address=ADDRESS, name=NAME)
    with patch("custom_components.lxd02.config_flow.async_discovered_service_info", return_value=[info]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LX-D02 0048"


async def test_bluetooth_discovery_flow(hass: HomeAssistant, fake_printer) -> None:
    info = SimpleNamespace(address=ADDRESS, name=NAME)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info)
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info)
    assert result["reason"] == "already_configured"


async def test_user_flow_ignores_other_devices(hass: HomeAssistant) -> None:
    other = SimpleNamespace(address="11:22:33:44:55:66", name="9529#123")
    with patch("custom_components.lxd02.config_flow.async_discovered_service_info", return_value=[other]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["reason"] == "no_devices_found"


# --- entities -------------------------------------------------------------------

async def test_entities_created(hass: HomeAssistant, printer_entry) -> None:
    expected = {
        "sensor": ["status", "battery", "receipts_printed", "paper_used", "last_printed"],
        "binary_sensor": ["in_range", "paper_out", "charging", "overheated"],
        "button": ["print", "feed", "refresh"],
        "text": ["form_title", "form_text", "form_qr", "form_icon"],
        "number": ["copies", "energy", "feed"],
        "select": ["form_size", "form_align"],
        "switch": ["stay_connected"],
        "image": ["preview"],
        "notify": ["receipt"],
    }
    for platform, keys in expected.items():
        for key in keys:
            assert eid(hass, platform, key), f"{platform}.{key} missing"
    assert state(hass, "sensor", "status") == "idle"
    assert state(hass, "sensor", "battery") == "unknown"  # not connected yet
    assert state(hass, "binary_sensor", "in_range") == "on"
    assert state(hass, "number", "energy") == "3"
    assert state(hass, "select", "form_size") == "normal"
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, ADDRESS), printer_entry.entry_id)
    assert device.model == "LX-D02"


async def test_print_button_prints_form(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await set_text(hass, "form_title", "Shopping")
    await set_text(hass, "form_text", "Milk, bread")
    await set_text(hass, "form_icon", "cart")  # "mdi:" is added
    await call(hass, "number", "set_value", {"entity_id": eid(hass, "number", "copies"), "value": 2})
    await call(hass, "number", "set_value", {"entity_id": eid(hass, "number", "energy"), "value": 5})
    await call(hass, "select", "select_option", {"entity_id": eid(hass, "select", "form_align"),
                                                 "option": "center"})
    assert state(hass, "text", "form_icon") == "mdi:cart"

    await press(hass, "print")

    assert len(fake_printer.jobs) == 2
    (width, height), kwargs = fake_printer.jobs[0]
    assert width == 384 and height > 100
    assert kwargs == {"energy": 5, "feed_mm": 0.0}
    assert state(hass, "sensor", "receipts_printed") == "2"
    assert float(state(hass, "sensor", "paper_used")) == pytest.approx(2 * (height / 8 + 10) / 1000, abs=0.001)  # + printer's own 10 mm
    assert state(hass, "sensor", "battery") == "87"
    assert state(hass, "binary_sensor", "paper_out") == "off"
    assert state(hass, "sensor", "status") == "idle"


async def test_text_rejects_unknown_icon(hass: HomeAssistant, printer_entry) -> None:
    with pytest.raises(ServiceValidationError, match="unknown MDI icon"):
        await set_text(hass, "form_icon", "mdi:not-an-icon")


async def test_print_button_with_empty_form(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    with pytest.raises(ServiceValidationError, match="Nothing to print"):
        await press(hass, "print")
    assert fake_printer.jobs == []


async def test_out_of_paper(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    fake_printer.status = Status.parse(bytes.fromhex("5a0257010000000300000040"))
    with pytest.raises(HomeAssistantError, match="out of paper"):
        await call(hass, DOMAIN, "print", {"text": "x"})
    assert fake_printer.jobs == []
    assert state(hass, "binary_sensor", "paper_out") == "on"
    assert state(hass, "sensor", "status") == "error"
    # Refreshing still works and keeps reporting the problem.
    await press(hass, "refresh")
    assert state(hass, "binary_sensor", "paper_out") == "on"


async def test_feed_button_and_action(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await press(hass, "feed")
    await call(hass, DOMAIN, "feed", {"length": 15})
    assert fake_printer.feeds == [20, 15]
    with pytest.raises(vol.Invalid):  # the printer always feeds at least 10 mm
        await call(hass, DOMAIN, "feed", {"length": 5})
    assert fake_printer.jobs == []
    assert state(hass, "sensor", "receipts_printed") == "0"
    assert float(state(hass, "sensor", "paper_used")) == pytest.approx(0.035)


async def test_preview_image(hass: HomeAssistant, printer_entry) -> None:
    before = state(hass, "image", "preview")
    await set_text(hass, "form_text", "Hello")
    image = await async_get_image(hass, eid(hass, "image", "preview"))
    assert image.content.startswith(b"\x89PNG")
    assert state(hass, "image", "preview") != before


async def test_notify_prints(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await call(hass, "notify", "send_message", {"entity_id": eid(hass, "notify", "receipt"),
                                                "title": "Reminder", "message": "Take out the trash"})
    assert len(fake_printer.jobs) == 1


async def test_connection_failure_sets_error(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    fake_printer.fail_with = OSError("boom")
    with pytest.raises(HomeAssistantError, match="Could not talk to the printer"):
        await call(hass, DOMAIN, "print", {"text": "x"})
    status = hass.states.get(eid(hass, "sensor", "status"))
    assert status.state == "error"
    assert "boom" in status.attributes["last_error"]


async def test_printer_error_reported(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    fake_printer.fail_with = PrinterError("handshake failed")
    with pytest.raises(HomeAssistantError, match="Printing failed: handshake failed"):
        await press(hass, "refresh")


# --- stay connected ---------------------------------------------------------------

async def wait_until(condition, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        assert loop.time() < deadline, "timed out"
        await asyncio.sleep(0.01)


async def test_stay_connected(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    manager = printer_entry.runtime_data
    switch = eid(hass, "switch", "stay_connected")
    assert hass.states.get(switch).state == "off"

    await call(hass, "switch", "turn_on", {"entity_id": switch})
    await wait_until(lambda: manager.connected)
    held = fake_printer.instances[-1]
    assert hass.states.get(switch).attributes["connected"] is True

    # Status frames pushed by the printer update the sensors live.
    held.on_status(Status.parse(bytes.fromhex("5a0232010100000300000040")))
    await hass.async_block_till_done()
    assert state(hass, "sensor", "battery") == "50"
    assert state(hass, "binary_sensor", "paper_out") == "on"
    assert state(hass, "binary_sensor", "charging") == "on"

    # Prints go over the held connection instead of a new one.
    held.on_status(Status.parse(STATUS))
    await call(hass, DOMAIN, "print", {"text": "- [ ] Milk"})
    assert len(fake_printer.jobs) == 1 and fake_printer.instances[-1] is held

    # A dropped connection is noticed and re-established.
    held.is_connected = False
    await wait_until(lambda: manager.connected and fake_printer.instances[-1] is not held)

    await call(hass, "switch", "turn_off", {"entity_id": switch})
    assert not manager.connected and not fake_printer.instances[-1].is_connected
    # Back to one connection per job.
    await call(hass, DOMAIN, "feed", {"length": 15})
    assert not fake_printer.instances[-1].is_connected


async def test_stay_connected_restored_and_unloaded(hass: HomeAssistant, fake_printer) -> None:
    from homeassistant.core import State
    from pytest_homeassistant_custom_component.common import mock_restore_cache

    mock_restore_cache(hass, [State("switch.lx_d02_0048_stay_connected", "on")])
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}, title="LX-D02 0048")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("switch.lx_d02_0048_stay_connected").state == "on"
    await wait_until(lambda: entry.runtime_data.connected)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not fake_printer.instances[-1].is_connected


# --- actions --------------------------------------------------------------------

async def test_print_action(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, ADDRESS), printer_entry.entry_id)
    await call(hass, DOMAIN, "print", {
        "device_id": device.id, "title": "Wi-Fi", "qr": "WIFI:T:WPA;S:Home;P:secret;;",
        "icon": "mdi:wifi", "size": "large", "copies": 3, "energy": 6, "feed": 0})
    assert len(fake_printer.jobs) == 3
    assert fake_printer.jobs[0][1] == {"energy": 6, "feed_mm": 0}


async def test_print_action_empty_fields_ignored(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    await call(hass, DOMAIN, "print", {"title": "Only a title", "icon": "", "qr": "", "image": None})
    assert len(fake_printer.jobs) == 1


async def test_print_action_picture(hass: HomeAssistant, printer_entry, fake_printer, tmp_path) -> None:
    from PIL import Image
    path = tmp_path / "photo.png"
    Image.new("RGB", (192, 96), "gray").save(path)
    with pytest.raises(ServiceValidationError, match="allowlist_external_dirs"):
        await call(hass, DOMAIN, "print", {"image": str(path)})
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await call(hass, DOMAIN, "print", {"image": str(path)})
    assert fake_printer.jobs[0][0] == (384, 192)
    with pytest.raises(ServiceValidationError, match="Could not open"):
        await call(hass, DOMAIN, "print", {"image": str(tmp_path / "missing.png")})


async def test_print_action_markdown(hass: HomeAssistant, printer_entry, fake_printer, tmp_path) -> None:
    text = "## Today\n- [ ] Milk\n- [x] Bread\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    await call(hass, DOMAIN, "print", {"text": text})
    await call(hass, DOMAIN, "print", {"text": text, "markdown": False})
    (_, md_height), (_, plain_height) = (job[0] for job in fake_printer.jobs)
    assert md_height != plain_height

    from PIL import Image
    Image.new("RGB", (64, 64), "black").save(tmp_path / "logo.png")
    with pytest.raises(ServiceValidationError, match="allowlist_external_dirs"):
        await call(hass, DOMAIN, "print", {"text": f"![logo]({tmp_path / 'logo.png'})"})
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await call(hass, DOMAIN, "print", {"text": f"![logo]({tmp_path / 'logo.png'})"})
    assert len(fake_printer.jobs) == 3


async def test_too_much_text_refused(hass: HomeAssistant, printer_entry, fake_printer) -> None:
    with pytest.raises(ServiceValidationError, match="Too much text"):
        await call(hass, DOMAIN, "print", {"text": "**x " * 3000})
    with pytest.raises(ServiceValidationError, match="Too much text"):
        await call(hass, "notify", "send_message", {"entity_id": eid(hass, "notify", "receipt"),
                                                    "message": "y" * 10001})
    assert fake_printer.jobs == []


async def test_print_action_unreachable(hass: HomeAssistant, printer_entry) -> None:
    with patch("custom_components.lxd02.manager.bluetooth.async_ble_device_from_address", return_value=None):
        with pytest.raises(HomeAssistantError, match="not reachable"):
            await call(hass, DOMAIN, "print", {"text": "x"})


async def test_print_action_wrong_device(hass: HomeAssistant, printer_entry) -> None:
    with pytest.raises(ServiceValidationError, match="Unknown device"):
        await call(hass, DOMAIN, "print", {"device_id": "nope", "text": "x"})
