# LX-D02 receipt printer for Home Assistant

A Home Assistant integration for the **LX-D02** Bluetooth thermal receipt
printer (58 mm paper, sold e.g. as Dolebo, used with the Funny Print app).
Print receipts from the UI, scripts, automations and notifications: an icon, a
title, Markdown text (lists, checklists, tables…), a QR code and a picture,
stacked in that order.

The printer is reached through Home Assistant's own Bluetooth: an adapter on
the Home Assistant machine, or an
[ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
near the printer. Tested with Home Assistant 2026.10.

The protocol and the receipt renderer come from the **LX-D02** project, which
also has a command-line tool and documents the printer's Bluetooth protocol.

## Install

1. Copy `custom_components/lxd02` into `/config/custom_components/` on Home
   Assistant (Samba, SSH or Studio Code Server add-on), or add this repository
   to HACS as a custom integration repository. Restart Home Assistant.
2. Turn the printer on and close the phone app. Under *Settings → Devices &
   services* an **LX-D02 Thermal Receipt Printer** appears as discovered: click
   **Add**. If not, *Add integration* → search "LX-D02".

The printer switches itself off after a few minutes idle, and stops
advertising while the phone app is connected.

## The printer device

- **Receipt form**: title, text, QR code and icon fields, text size and
  alignment, copies, a live **Receipt preview** and a **Print receipt** button
- **Feed paper** (20 mm) and **Refresh status** buttons
- sensors for status, battery, receipts printed, paper used and last printed;
  binary sensors for in range, paper out, charging and overheated
- settings for **Print darkness** (1–6), **Feed after printing** (extra paper
  on top of the 10 mm the printer always feeds after a job; default 0) and
  **Stay connected**
- a `notify` entity: `notify.send_message` prints the title and message

### Stay connected

The printer only reports battery, paper and charging while something is
connected to it. By default Home Assistant connects only for each print or
refresh, so those sensors show the state from the last connection, and the
phone app can use the printer in between.

Turn on **Stay connected** (under the device's configuration) to hold the
connection instead: battery, paper, charging and overheating then update every
2–3 seconds, prints start without connecting first, and Home Assistant
reconnects whenever the printer comes back after being off. While it is on, the
phone app and other computers can't reach the printer, since it accepts only
one connection. The switch's `connected` attribute shows whether the
connection is up right now.

## Actions

```yaml
action: lxd02.print
data:
  icon: mdi:cart
  title: Shopping
  text: |                # Markdown
    - [ ] Milk
    - [ ] Bread
    - [ ] Coffee, **dark roast**
  markdown: true     # false prints the text as written
  qr: https://example.com/list
  size: normal       # small / normal / large
  align: left        # left / center / right
  copies: 1
  energy: 3          # optional, 1-6
  feed: 0            # optional, extra mm of blank paper after it
```

`image:` prints a picture from the Home Assistant host, for example
`/config/www/photo.jpg`; its folder must be listed under
`allowlist_external_dirs` in `configuration.yaml`.

`lxd02.feed` with `length:` (mm) advances blank paper. After every job the
printer feeds about 10 mm by itself so the last line clears the tear bar, so
10 mm is the shortest feed. With several printers, pass `device_id` to either
action.

## Markdown

The `text` field, the form's text and notify messages are Markdown:

| Markdown | Prints as |
|---|---|
| `# H1`, `## H2`, `### H3` | headings (H1 centred, H1/H2 underlined) |
| `**bold**`, `*italic*` / `_italic_`, `~~strike~~`, `` `code` `` | inline styles (`code` on a light gray background) |
| `[text](url)` | underlined text |
| `- item`, `* item`, `1. item` | bullet and numbered lists; indent to nest |
| `- [ ] task`, `- [x] done` | checkboxes, empty or ticked |
| `> text` | quote with a bar on the left |
| ```` ``` ```` fenced block | monospace box, spaces kept |
| `---` | dashed tear line |
| `\| a \| b \|` + `\|---\|---\|` | table with a bold header; `:--`, `:-:`, `--:` align columns |
| `![alt](path)` | picture from a path in an `allowlist_external_dirs` folder |

Unlike standard Markdown, every line break is kept. Use `markdown: false` to
print the text exactly as written.

## Troubleshooting

**"… is not reachable" / Status unavailable**: the printer is off (it powers
off when idle), the phone app is connected to it, or no Bluetooth adapter or
proxy is in range.

**Feed after printing still adds 12 mm after updating**: older versions
defaulted to 12 mm, and the setting keeps its value. Set it to 0.

## Development

`custom_components/lxd02/protocol.py`, `receipt.py`, `markdown.py` and
`assets/` are copies from the LX-D02 package (`src/lxd02/`). Change them there
and copy them here. With LX-D02 checked out next to this project (or
`LXD02_PACKAGE` pointing at its `src/lxd02`), a test fails if the copies
differ.

The tests cover the config flow, every entity, the actions, notify, preview,
Stay connected and errors, with a fake printer. They need Linux (or WSL) with
Python 3.14:

```bash
pip install pytest-homeassistant-custom-component qrcode pillow
```
```bash
pytest
```

Home Assistant's Bluetooth component also needs its own requirements: install
those listed in the `manifest.json` of the `bluetooth`, `bluetooth_adapters`,
`usb` and `hassio` components.
