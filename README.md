[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

[![CodeQL](https://github.com/jacobbjerregaard/homeassistant-carlo-gavazzi-em300/actions/workflows/codeql.yml/badge.svg)](https://github.com/jacobbjerregaard/homeassistant-carlo-gavazzi-em300/actions/workflows/codeql.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Known Vulnerabilities](https://snyk.io/test/github/jacobbjerregaard/homeassistant-carlo-gavazzi-em300/badge.svg)](https://snyk.io/test/github/jacobbjerregaard/homeassistant-carlo-gavazzi-em300)

# Carlo Gavazzi EM300 / ET300 for Home Assistant

A Home Assistant custom integration for Carlo Gavazzi **EM300** and **ET300**
series energy meters, read over Modbus RTU. It polls the meter locally -- no
cloud, no account -- and exposes its measurements as sensors.

## Supported meters

| Series | Identification code | Notes |
| --- | --- | --- |
| EM330 | 331, 332 | |
| EM331 | 355 | |
| EM340 | 341 | |
| EM341 | 346 | |
| ET330 | 335, 336 | |
| ET340 | 345 | |

The meter is identified at setup from its Carlo Gavazzi identification code
(protocol table 2.8-2). That selects which registers are polled: the run-hour
meter is documented as ET-series and EM330 only, and the per-phase *exported*
energy totalizers as ET-series only, so those entities are not created on an
EM340 where they could only ever report zero.

The answer is remembered on the config entry, so a meter that fails the
identification read once keeps the entity set it had rather than growing a
batch of entities it can never populate. A meter that has *never* answered the
read gets the full register set, which is the safer default.

> An EM340 reporting code **340** is a pre-production engineering sample that
> stores 32-bit values MSW-first instead of LSW-first. It is detected and
> warned about in the log, but its multi-word readings will be wrong.

## Connection

Two transports are supported:

* **Serial (RS485)** -- a USB-to-RS485 adapter wired to the meter directly.
* **Network (Modbus TCP)** -- an RS485-to-Ethernet gateway. Pick *Modbus TCP*
  framing for a native gateway, or *Modbus RTU over TCP* for a transparent
  serial bridge.

The serial settings and the Modbus address must match what is programmed into
the meter's own serial port configuration menu. The factory defaults are
9600 baud, no parity, 1 stop bit, 8 data bits, address 1.

## Installation

### HACS

1. In HACS, choose **Integrations -> ⋮ -> Custom repositories**.
2. Add `https://github.com/jacobbjerregaard/homeassistant-carlo-gavazzi-em300`
   with category **Integration**.
3. Install **Carlo Gavazzi EM300**, then restart Home Assistant.
4. Go to **Settings -> Devices & services -> Add integration** and search for
   *Carlo Gavazzi EM300*.

> HACS shows a "brands" warning for this repository. It is cosmetic: the
> integration installs and works normally. Clearing it requires Carlo Gavazzi's
> own icon and logo to be accepted into the
> [home-assistant/brands](https://github.com/home-assistant/brands) repository,
> which is only a prerequisite for listing in the HACS default store.

### Manual

Copy `custom_components/carlo_gavazzi_em300` into your Home Assistant
`config/custom_components/` directory and restart.

Requires Home Assistant 2025.3 or newer.

## Entities

Only the system aggregates and the main energy totalizers are enabled by
default. Everything else is created but disabled, so the per-phase breakdown
is one click away in the entity registry without cluttering a typical
installation with forty-odd entities.

| Entity | Unit | Enabled by default |
| --- | --- | --- |
| Active power | W | Yes |
| Apparent power | VA | Yes |
| Exported energy | kWh | Yes |
| Exported reactive energy | kvarh | Yes |
| Frequency | Hz | Yes |
| Imported energy | kWh | Yes |
| Imported reactive energy | kvarh | Yes |
| Power factor | - | Yes |
| Reactive power | var | Yes |
| Voltage L-L | V | Yes |
| Voltage L-N | V | Yes |
| Active power L1 | W | No |
| Active power L2 | W | No |
| Active power L3 | W | No |
| Apparent power L1 | VA | No |
| Apparent power L2 | VA | No |
| Apparent power L3 | VA | No |
| Current L1 | A | No |
| Current L2 | A | No |
| Current L3 | A | No |
| Exported energy L1 | kWh | No |
| Exported energy L2 | kWh | No |
| Exported energy L3 | kWh | No |
| Imported energy (partial) | kWh | No |
| Imported energy L1 | kWh | No |
| Imported energy L2 | kWh | No |
| Imported energy L3 | kWh | No |
| Imported energy tariff 1 | kWh | No |
| Imported energy tariff 2 | kWh | No |
| Imported reactive energy (partial) | kvarh | No |
| Peak power demand | W | No |
| Phase sequence | - | No |
| Power demand | W | No |
| Power factor L1 | - | No |
| Power factor L2 | - | No |
| Power factor L3 | - | No |
| Reactive power L1 | var | No |
| Reactive power L2 | var | No |
| Reactive power L3 | var | No |
| Run hours | h | No |
| Voltage L1-L2 | V | No |
| Voltage L1-N | V | No |
| Voltage L2-L3 | V | No |
| Voltage L2-N | V | No |
| Voltage L3-L1 | V | No |
| Voltage L3-N | V | No |

The polling interval defaults to 30 seconds and can be changed under the
integration's **Configure** option. The meter refreshes its own measurements
about once a second, so polling faster than that only adds bus traffic.

## Changing the connection

If the serial port is renamed or the gateway moves to a new address, use
**Reconfigure** on the device rather than deleting and re-adding it. The entry
keeps its identity, so all history and any automations referencing its entities
survive. A meter can also be moved between RS485 and a TCP gateway this way.

When both the entry and the meter report a serial number, they have to match:
reconfiguring points an entry at the same meter somewhere else, and Home
Assistant will refuse to graft one meter's history onto another. Meters that do
not implement the serial-number block are identified only by where they live,
so there is nothing to check and the move goes through.

## Verified against hardware

The register map was checked against a live **EM340, firmware B4**, reached
through a Modbus TCP gateway. What that run confirmed:

* Word order. V L1-N reads 238.6 V least-significant-word first, and
  15,636,889.6 V the other way round.
* The value weights, each by an independent cross-check: current at Ampere*1000
  (238 V x 0.016 A = 3.8 VA against a reported 3.9 VA), power factor at PF*1000
  (|W|/VA = 0.795 against a reported 0.799), frequency at Hz*10.
* The addresses, by reading the same measurements again through table 2.6-1 and
  comparing, and by checking that the per-phase energy totalizers sum to the
  system total (they agreed to 0.013%, the meter's own rounding).
* Model detection. Identification code 341 selected EM340 and correctly
  narrowed the poll to 42 of the 46 registers, dropping the four the protocol
  documents as ET-series or EM330 only.
* The serial number decoder, on a real seven-character serial.

Gateways vary: that one needed **Modbus TCP** framing, the default. A poll of
five requests took about 1.25 s through the gateway, so the 30 s default
interval leaves plenty of headroom.

## How the register map works

Everything the integration reads comes from table 2.4-1 of *EM300 Series and
ET300 Series Communication Protocol*, version 2 revision 17. A few properties
of that map are worth knowing:

* Every measurement is a scaled integer -- `INT16` or `INT32`. The protocol's
  format table lists IEEE754 single precision, but no register actually uses
  it.
* 32-bit values are stored **least-significant word first**.
* Each value carries a "value weight": the raw integer is divided by 10 for
  volts, watts, VA, var, hertz, kWh and kvarh, by 1000 for amperes and power
  factor, and by 100 for the run-hour meter.
* A single request may read at most 20 words. Section 1.2.1 contradicts
  itself here -- its prose says 50, its request frame says 1 to 0x14 -- and
  the frame is what goes on the wire, so the lower limit is used.
* Registers the protocol marks *"Not available, value =0"* are left out
  entirely.
* The identification code at word `0x000B` doubles as the high word of
  V L3-L1, which is why the protocol says to read it one word at a time. The
  integration keeps it out of batched reads for that reason.

The 3-decimal totalizers of tables 2.5-1 and 2.5-2 are **not** exposed. Their
availability depends on the meter's manufacturing date rather than its model,
and reading an address a meter does not implement raises an illegal-data-address
exception that would fail the whole batch.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test_ha.txt -r requirements_lint.txt
pytest
ruff check . && ruff format --check . && mypy
```

The suite has two layers. `tests/` exercises the protocol handling on its own
-- the `api` package is registered as a standalone namespace module, so no
Home Assistant is needed. `tests/integration/` drives real config-entry setup,
the coordinator and the sensor platform against a faked transport, and is
skipped automatically when Home Assistant is not installed.

`tests/test_register_map.py` transcribes table 2.4-1 a second time,
independently of the map itself, so a typo in an address or a value weight
fails the suite rather than producing plausible but wrong readings.

## License

Apache License 2.0. See [LICENSE](LICENSE).

This project is not affiliated with or endorsed by Carlo Gavazzi.
