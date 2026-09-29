# How it was tested

Everything was tested with one ESP32, one IR receiver, one IR transmitter and a laptop running Home Assistant and ESPHome. The receiver listens to the bridge's own LED, so every command sent can be checked. Later tests used the TV and the Panasonic air conditioner at home.

Test scripts are in `measure/`, results in `measure/results/`. The C++ tests in `firmware/tests/` build with plain `g++` on a laptop.

## What was checked

| Test | Result |
|---|---|
| Send a code and read it back | every code came back correct |
| Change air conditioner settings one at a time | every setting decoded correctly |
| Replay captures recorded from real remotes | all decoded correctly |
| Learn 92 real remote codes (Flipper-IRDB, 12 AC and 7 TV brands), decode the copy with IRremoteESP8266 | 80 of 92 match, 74 when the copy is learned again |
| Learn the TV power button, send it 10 times | the TV switched every time |
| Learn the Panasonic remote | same 216-bit frame as IRremoteESP8266 reads |
| Panasonic climate entity: all 5,400 states against IRremoteESP8266 | all match, and the two real remote frames match byte for byte |
| Stop Home Assistant, send from the bridge's web page | sent and heard back |
| Cut the internet | everything kept working |
| Unplug the ESP32 or turn off WiFi | recovers on its own once back |
| Unplug the ESP32 while sending | every lost command raised an alert |
| OTA update with a wrong password | rejected |

## Fixes found while testing

The ESPHome air conditioner component had two problems: what it sent was not recognised by an independent decoder, and it missed codes the receiver had actually heard.

Without the alert automation, Home Assistant takes a long time to notice the ESP32 is gone, and commands sent in that time are lost without any error.

The IR receiver moves each pulse edge by up to a few carrier cycles, so a raw copy of a code only decoded 41 of 92 times. The bridge now groups pulses of similar length and stores the middle value of each group, with a small correction measured from its own LED. The settings were picked on 13 remotes and checked on the other 12 (42 of 44).

## Not covered

- Range in metres. The TV needs the bridge close, the wall-mounted air conditioner was out of reach.
- A real remote updating the Panasonic entity in Home Assistant.
- A real remote and Home Assistant sending at the same moment.
- Philips RC6 codes and Hitachi 296-bit codes do not learn cleanly.
