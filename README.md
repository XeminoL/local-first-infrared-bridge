An ESP32 infrared bridge for Home Assistant that keeps working with the internet cut off.

It learns and sends remote-control codes, drives a Daikin air conditioner as a climate entity, and warns within 2 seconds when a command never left the LED.

```
Home Assistant --ESPHome API over WiFi--> ESP32 --38 kHz--> IR LED  ))) appliance
       ^                                    ^
       |                                    +---- IR receiver hears the LED (echo)
       +---- "IR command not confirmed" if no echo within 2 s
```

![Home Assistant switches the remote to Heat, Fan and Off; the listen-only Virtual Daikin follows each change](docs/media/demo.gif)

The same clip at full resolution: [docs/media/demo.mp4](docs/media/demo.mp4).

## Hardware

![ESP32 DevKit with the IR receiver and IR transmitter modules wired up](docs/media/hardware.jpg)

| Part | Pin | ESP32 |
|---|---|---|
| IR receiver module (38 kHz) | `VCC` | `3V3` |
| | `GND` | `GND` |
| | `OUT` | `D27` |
| IR transmitter module | `VCC` | `VIN` (5 V from USB) |
| | `GND` | `GND` |
| | `DAT` | `D4` |

Board: DOIT ESP32 DevKit V1. The receiver runs on 3.3 V because its `OUT` swings to whatever `VCC` is, and the ESP32 pins only take 3.3 V. The board has a single `3V3` pin, so the transmitter takes `VIN`; it only receives a signal from `D4`, so 5 V there is safe.

## Firmware

`firmware/ir-bridge.yaml`, ESPHome 2026.8.2 on ESP-IDF 5.5.5.

- `Daikin Remote`: climate entity that transmits.
- `Virtual Daikin`: listen-only climate entity that decodes whatever the receiver hears. It stands in for the air conditioner during tests.
- `IR echo`: event fired when the receiver hears a Daikin state frame, including the bridge's own.
- `Send test code` and `IR received`: NEC loopback used by the measurement scripts.
- `send_raw` action: transmits a list of raw timings, used to replay captures of real remotes.

`firmware/components/daikin/` is a fork of ESPHome's `daikin` component, loaded through `external_components`. It changes two things, both explained in [docs/measurements.md](docs/measurements.md):

1. Transmit starts with the 5-bit leader that real Daikin remotes send.
2. Receive tells 0 from 1 with a single 865 µs threshold instead of a ±25% window per bit.

## Running

ESPHome in Docker, with the config folder mounted and the build cache kept in a volume:

```bash
docker run -d --name esphome --network host --restart unless-stopped \
  -e IDF_GITHUB_ASSETS=dl.espressif.com/github_assets \
  -v "$PWD/firmware:/config" -v esphome_build:/config/.esphome \
  ghcr.io/esphome/esphome:stable
```

`IDF_GITHUB_ASSETS` points the toolchain download at Espressif's mirror. From here GitHub gave about 100 KB/s and the mirror 5.4 MB/s, which is the difference between an hour and a minute on the first build.

`firmware/secrets.yaml` is not in the repo. It needs `wifi_ssid`, `wifi_password`, `ota_password`, `api_encryption_key` (32 random bytes, base64) and `fallback_ap_password`.

Flash over USB the first time from the dashboard (Install, then Plug into this computer). Add the device to Home Assistant by IP rather than `ir-bridge.local` if Home Assistant runs inside WSL, since mDNS does not cross the WSL NAT. Then import `homeassistant/ir_command_confirmation.yaml` as an automation.

The ESP32 only does 2.4 GHz WiFi, and `power_save_mode: none` is set on purpose: with the default power save, ping took 149 ms and lost 10% of packets; without it, 22.5 ms and none lost.

## Results

| | |
|---|---|
| NEC loopback, 100 presses | 100/100, median 111 ms |
| Daikin, one field changed per step, 110 steps | 110/110, median 622 ms |
| Captures of 6 real Daikin remotes, replayed | 71/71 (unmodified ESPHome: 0/12) |
| Internet cut off | NEC 100/100, Daikin 54/55, same latency |
| Power pulled, lost commands flagged | 10/10, 2.0 s after the command (107 s without the echo check) |
| Range | not measured |

![Home Assistant notification: IR command not confirmed](docs/media/not-confirmed-alert.png)

Method, evidence files and limits are in [docs/measurements.md](docs/measurements.md).

## Measurement scripts

`measure/` needs Python 3.11+ with `aiohttp`, and `HA_TOKEN` set to a Home Assistant long-lived access token. `HA_URL` defaults to `http://localhost:8123`.

| Script | Does |
|---|---|
| `loopback.py` | presses `Send test code` and times the NEC round trip |
| `climate_sweep.py` | changes one field of `Daikin Remote` per step and checks `Virtual Daikin` |
| `replay_irdb.py` | replays real remote captures through `send_raw` |
| `recovery.py usb\|wifi\|ha` | breaks one thing and times how long until commands work again |
| `confirmation_test.py` | pulls power and checks every lost command raises an alert |
| `offline_test.ps1 -Esp32Address <ip>` | runs the loopback and climate tests only if the internet is unreachable |
| `range_test.py` | mirror range test, with a control run for side leakage |
| `ota_probe.py <ip>` | checks whether the OTA port asks for a password, without uploading |
| `irdb_decode.py` | decodes Flipper IR captures into bytes |
| `daikin_crosscheck.py` | encodes Daikin states from the component source and decodes them with IRremoteESP8266 (build it first with `build_irremote_decoder.sh` inside WSL) |

`bridge.py`, `ha_client.py`, `climate_state.py`, `results.py` and `prompt.py` are shared by the scripts. Results are written to `measure/results/`.

## Licenses

GPLv3, see `LICENSE`. `firmware/components/daikin/` is derived from ESPHome's C++ code, which is GPLv3 as well (`LICENSE-ESPHome.md` there). The remote captures in `measure/irdb/` come from Flipper-IRDB under CC0. IRremoteESP8266 (LGPL-2.1) is used as an external tool and is not included.
