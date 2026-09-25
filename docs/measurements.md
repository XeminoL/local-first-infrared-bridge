# How it was tested

Everything was tested with one ESP32, one IR receiver, one IR transmitter and a laptop running Home Assistant and ESPHome. The receiver listens to the bridge's own LED, so every command sent can be checked. Results are compared against things I did not write: captures from real remotes and an independent IR library.

Test scripts are in `measure/`, results in `measure/results/`.

## What was checked

| Test | Result |
|---|---|
| Send a code and read it back | every code came back correct |
| Change air conditioner settings one at a time | every setting decoded correctly |
| Replay captures recorded from real remotes | all decoded correctly |
| Cut the internet | everything kept working |
| Unplug the ESP32 or turn off WiFi | recovers on its own once back |
| Unplug the ESP32 while sending | every lost command raised an alert |
| OTA update with a wrong password | rejected |

## Fixes found while testing

The ESPHome air conditioner component had two problems: what it sent was not recognised by an independent decoder, and it missed codes the receiver had actually heard. Both are fixed in `firmware/components/`.

Without the alert automation, Home Assistant takes a long time to notice the ESP32 is gone, and commands sent in that time are lost without any error. The automation in `homeassistant/ir_command_confirmation.yaml` covers that gap.

## Not covered

- Not tried on a real appliance yet. The echo proves the LED fired, not that a device accepted the command.
- Range was not measured.
- A real remote and Home Assistant sending at the same moment was not tested.
