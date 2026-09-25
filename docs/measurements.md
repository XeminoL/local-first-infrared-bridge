# Measurements

All tests ran on 25 September 2026 with the parts I own: one ESP32, one IR receiver module, one IR transmitter module and a laptop running Home Assistant 2026.9.1 and ESPHome 2026.8.2 in Docker under WSL. I did not use a real air conditioner or a real remote. Every check below compares against something I did not write: captures recorded from real remotes, or an independent IR library.

Unless noted, the two modules sat about 20 cm apart facing each other, on a phone hotspot (2.4 GHz). Every CSV named here is in `measure/results/`.

## Loopback and latency

`measure/loopback.py` presses the `Send test code` button through the Home Assistant websocket, the ESP32 sends NEC `0x1234 / 0x78AB`, and the receiver has to decode the same two numbers and report `correct`. Both timestamps come from the laptop clock.

100 presses: 100 correct, median 111.1 ms, p90 164.8 ms, p99 249.0 ms, one outlier at 1395.7 ms that I could not explain (`20260925-124055-loopback-hand-span.csv`). A full NEC frame takes about 67.5 ms on air and the receiver waits 10 ms of silence before closing it, so roughly 33 ms is network and Home Assistant. That split is calculated, not measured.

WiFi power save, 30 pings each, same spot: median 149 ms with 3 of 30 lost by default, median 22.5 ms with none lost after `power_save_mode: none`. The signal was weaker on the second run (-56 dB against -42 to -49 dB).

## Daikin: two problems in ESPHome's component

### Missing leader on transmit

I rebuilt the exact waveform ESPHome's `daikin.cpp` transmits and fed it to IRremoteESP8266 (commit `1e2f0f3`, 23 August 2026), built on the laptop with `measure/build_irremote_decoder.sh`. The only change to its `mode2_decode` tool is the split threshold (20 ms to 60 ms, because Daikin frames are 25 to 35 ms apart) and one extra line printing its decoded description.

`measure/daikin_crosscheck.py` reads the constants and the `remote_state` array straight from the component source and sweeps 1,301 states: cool, heat and heat_cool at 10 to 30 °C with 5 fan speeds and 4 swing modes, plus dry, fan_only and off.

| Source | Recognised as DAIKIN | Bytes and meaning match |
|---|---|---|
| ESPHome as shipped | 0 / 1,301 | 0 |
| Fork with the leader | 1,301 / 1,301 | 1,301 |

IRremoteESP8266's `decodeDaikin()` requires a 5-bit zero leader followed by about 29 ms of silence before the first frame. All three 280-bit Daikin remotes in Flipper-IRDB send it; ESPHome does not. With the leader added, byte content and timing agree with the independent decoder on every state. The leader space in the fork is 25 ms, the median of what the real remotes send (24.98, 25.10 and 25.43 ms).

My first run reported 780 mismatches on fan speed. That was my expectation table using raw nibbles (3, 5, 7) where IRremoteESP8266 numbers speeds 1 to 5.

### Receive window too narrow

`measure/climate_sweep.py` changes one field of `Daikin Remote` per step and waits up to 3 s for `Virtual Daikin` to decode the same state.

| Firmware | Steps matched |
|---|---|
| ESPHome as shipped | 24 / 55 |
| Same, 20 steps with the log running | 7 / 20 |
| Fork, 20 steps | 20 / 20 |
| Fork, 2 rounds | 110 / 110, median 622 ms, p90 650 ms, max 717 ms |

Every failure was a silent miss. The ESP32 log showed the receiver getting all three frames every time, and I decoded all 23 state frames from the Pronto dumps in the log: every one had correct bytes and checksum. The pattern was exact: frames whose longest bit-0 space was at most 473 µs were accepted, frames with one at 500 µs or more were dropped. ESPHome accepts a bit 0 only between 270 and 450 µs (360 µs ±25%), and the receiver module stretches spaces, measuring 316 to 526 µs for a 360 µs transmission.

The fork classifies each bit with one threshold at 865 µs, halfway between the zero and one spaces. Bad frames are still rejected by the fixed first five bytes and the checksum. I tried the threshold on the 23 logged frames before flashing; all 23 decoded. The transmit side still gives 1,301 / 1,301 after the change. Of the 622 ms median, 424 to 440 ms is the Daikin message itself on air.

Files: `20260925-133904-daikin-1round.csv`, `20260925-134119-daikin-dumpall-log.csv`, `20260925-135044-daikin-threshold-full.csv`.

### Real remotes, replayed

`measure/replay_irdb.py` sends each capture from `measure/irdb/daikin/` through the `send_raw` action, works out the state the remote meant from its bytes, and checks `Virtual Daikin`. 71 signals from 6 remotes; 12 signals from 3 files use a different protocol and were skipped.

| Firmware | Result |
|---|---|
| Fork | 71 / 71 |
| ESPHome as shipped | 0 / 12 |

The first fork run gave 47 / 71. Every failure was an ARC480 command at a half degree (23.5, 18.5, 25.5 °C), and the only difference was temperature: `Virtual Daikin` used the default 1 °C step and rounded when reporting. Setting `temperature_step` to 0.5 fixed all 36 ARC480 signals.

For the unmodified component I stopped after 12 signals. The log for the last 4 shows all frames received with correct bytes and checksum, and no state published: marks measured 316 to 526 µs and bit-0 spaces 342 to 526 µs, outside both of ESPHome's windows.

These captures already went through one receiver when they were recorded, and replaying them sends them through mine, so the distortion is applied twice. The 0 / 12 may be worse than pressing a real remote directly.

## Without internet

`measure/offline_test.ps1` refuses to run while 1.1.1.1, 8.8.8.8 or google.com answer, runs the NEC and Daikin tests, then checks the internet is still unreachable at the end.

| | With internet | Without |
|---|---|---|
| NEC, 100 presses | 100/100, median 111.1 ms | 100/100, median 113.5 ms |
| Daikin, 55 steps | 110/110 (2 rounds), median 622 ms | 54/55, median 622 ms |

The first offline run was discarded: Windows moved the laptop onto another saved WiFi network that still had internet, and 8 presses in a row failed. Turning off "Connect automatically" for that network avoided it.

## Recovery

`measure/recovery.py` presses the test button every 2.5 s while one thing is broken.

| Fault | Home Assistant marks it unavailable after | Presses lost with no error | Working again after the fix |
|---|---|---|---|
| USB pulled | 107.5 s | 42 | 11.2 s |
| Hotspot off | 99.9 s | 39 | at most about 18 s |
| Home Assistant restarted | | | 13.1 s |

The ESPHome API client in Home Assistant (aioesphomeapi 46.2.0) pings every 20 s and gives up after 20 × 4.5 = 90 s without an answer, so a dead device goes unnoticed for 90 to 110 s. During that time `call_service` succeeds and the command goes nowhere. Presses sent after the entity became unavailable also returned no error through the API.

The WiFi recovery time is not a real measurement. My script stopped probing while it waited for Enter, and the network came back inside that gap, so the first probe after Enter already worked. I fixed the script afterwards and did not repeat the test.

## Echo as confirmation

The receiver hears the bridge's own LED, so every command has an echo. `on_raw` fires the `IR echo` event for any received block of 300 to 320 timings starting with a mark above 2,500 µs (the Daikin state frame). The automation in `homeassistant/ir_command_confirmation.yaml` triggers on `call_service` for the climate entity and waits 2 s for the echo. It triggers on the service call because a dead ESP32 never updates the entity's state.

`measure/confirmation_test.py`, one `set_temperature` every 4 s:

| | Result |
|---|---|
| ESP32 plugged in, 5 commands | 5 confirmed, 0 false alerts |
| USB pulled, 10 commands | 10 accepted by Home Assistant, 0 echoes, 10 alerts, median 2,006 ms after the command |
| Plugged back in | confirmed again after 7.5 s |

File: `20260925-155043-confirmation.csv`.

## OTA password

`measure/ota_probe.py` runs the ESPHome OTA handshake from `espota2.py` up to authentication and disconnects before any upload.

| | Device answer |
|---|---|
| Before adding a password | `0x41`, no authentication |
| With a wrong password | `0x02` SHA256 challenge, then `0x82` rejected |
| With the right password | `0x02`, then `0x41` accepted |

## Range

Not measured. I planned to aim both modules at a mirror and move it away step by step, but had no mirror. A phone screen reflects about 4% where a mirror reflects over 90%, so it would not give a usable number.

With both modules facing the same way and no mirror, the receiver decoded 30/30 NEC and 10/10 Daikin from light leaking sideways out of the LED. With a book standing between them it decoded 0/30 and 0/10, so walls in the room did not reflect enough to matter. `measure/range_test.py` and `results/range-summary.csv` are ready for the mirror test.

## What these tests do not cover

- No real air conditioner. The echo proves the LED fired; it does not prove an appliance accepted the command.
- Daikin has several remote variants. The fork matches the 280-bit three-frame type; ARC480 remotes send one 19-byte frame and ESPHome's transmit side does not produce that.
- The fork still differs from real 280-bit remotes in bytes 15 and 16 of the state frame (`c0 00` against `c1 80`) and in pulse widths by up to about 21%. IRremoteESP8266 accepts it; whether a real indoor unit does is unknown.
- The 38 kHz carrier was not measured. The receiver only reports whether a signal is present.
- A real remote and Home Assistant sending at the same moment was not tested; that needs a second LED.
- The echo is recognised by frame length, so a real remote pressed at the same moment would also count as an echo.
- Range was not measured.
