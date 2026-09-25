import argparse
import itertools
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

WSL_DISTRO = "Ubuntu"
DECODER = "~/irremote/tools/mode2_decode_long"
MESSAGE_SEPARATOR_US = 65535
FORK_DIR = Path(__file__).resolve().parent.parent / "firmware" / "components" / "daikin"
UPSTREAM_DIR = "/esphome/esphome/components/daikin"
ESPHOME_CONTAINER = "esphome"

FIRST_FRAME_END = 8
STATE_FRAME_START = 16
MODE_INDEX, TEMPERATURE_INDEX, FAN_INDEX, SWING_INDEX, CHECKSUM_INDEX = 21, 22, 24, 25, 34
FAN_ONLY_TEMPERATURE_BYTE = 0x32
DRY_TEMPERATURE_BYTE = 0xC0

SWING_BITS = {"off": 0x0000, "vertical": 0x0F00, "horizontal": 0x000F, "both": 0x0F0F}
IRREMOTE_MODE = {"cool": 3, "heat": 4, "dry": 2, "heat_cool": 0, "fan_only": 6, "off": 0}
IRREMOTE_FAN = {"auto": 10, "quiet": 11, "low": 1, "medium": 3, "high": 5}


def read_source(which):
    if which == "fork":
        return (FORK_DIR / "daikin.h").read_text(encoding="utf-8"), (FORK_DIR / "daikin.cpp").read_text(encoding="utf-8")
    texts = []
    for name in ("daikin.h", "daikin.cpp"):
        result = subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "docker", "exec", ESPHOME_CONTAINER,
                                 "cat", f"{UPSTREAM_DIR}/{name}"], capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"cannot read upstream {name}: {result.stderr.strip()}")
        texts.append(result.stdout)
    return tuple(texts)


class Protocol:
    def __init__(self, header, source):
        constants = {name: int(value, 0) for name, value in
                     re.findall(r"const\s+uint\d+_t\s+(DAIKIN_\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*;", header)}
        base = re.search(r"remote_state\[35\]\s*=\s*\{([^}]*)\}", source)
        if not base:
            sys.exit("remote_state initialiser not found in daikin.cpp")
        self.base_state = [int(value, 0) for value in base.group(1).replace("\n", " ").split(",")]
        self.constants = constants
        self.leader_bits = constants.get("DAIKIN_LEADER_BITS", 0)
        self.mode_bytes = {"cool": constants["DAIKIN_MODE_COOL"], "heat": constants["DAIKIN_MODE_HEAT"],
                           "dry": constants["DAIKIN_MODE_DRY"], "heat_cool": constants["DAIKIN_MODE_AUTO"],
                           "fan_only": constants["DAIKIN_MODE_FAN"]}
        self.fan_bytes = {"auto": constants["DAIKIN_FAN_AUTO"], "quiet": constants["DAIKIN_FAN_SILENT"],
                          "low": constants["DAIKIN_FAN_1"], "medium": constants["DAIKIN_FAN_3"],
                          "high": constants["DAIKIN_FAN_5"]}

    def state(self, mode, temperature, fan, swing):
        const = self.constants
        state = list(self.base_state)
        state[MODE_INDEX] = const["DAIKIN_MODE_OFF"] if mode == "off" else const["DAIKIN_MODE_ON"] | self.mode_bytes[mode]
        if mode == "fan_only":
            state[TEMPERATURE_INDEX] = FAN_ONLY_TEMPERATURE_BYTE
        elif mode == "dry":
            state[TEMPERATURE_INDEX] = DRY_TEMPERATURE_BYTE
        else:
            state[TEMPERATURE_INDEX] = round(min(max(temperature, const["DAIKIN_TEMP_MIN"]), const["DAIKIN_TEMP_MAX"])) << 1
        fan_speed = (self.fan_bytes[fan] << 8) | SWING_BITS[swing]
        state[FAN_INDEX] = fan_speed >> 8
        state[SWING_INDEX] = fan_speed & 0xFF
        state[CHECKSUM_INDEX] = sum(state[STATE_FRAME_START:CHECKSUM_INDEX]) & 0xFF
        return bytes(state)

    def timings(self, state):
        const = self.constants
        timings = []
        if self.leader_bits:
            for _ in range(self.leader_bits):
                timings.extend([const["DAIKIN_BIT_MARK"], const["DAIKIN_ZERO_SPACE"]])
            timings.extend([const["DAIKIN_BIT_MARK"], const["DAIKIN_LEADER_SPACE"]])

        def frame(data):
            timings.extend([const["DAIKIN_HEADER_MARK"], const["DAIKIN_HEADER_SPACE"]])
            for byte in data:
                for bit in range(8):
                    timings.extend([const["DAIKIN_BIT_MARK"],
                                    const["DAIKIN_ONE_SPACE"] if byte >> bit & 1 else const["DAIKIN_ZERO_SPACE"]])

        frame(state[:FIRST_FRAME_END])
        timings.extend([const["DAIKIN_BIT_MARK"], const["DAIKIN_MESSAGE_SPACE"]])
        frame(state[FIRST_FRAME_END:STATE_FRAME_START])
        timings.extend([const["DAIKIN_BIT_MARK"], const["DAIKIN_MESSAGE_SPACE"]])
        frame(state[STATE_FRAME_START:])
        timings.append(const["DAIKIN_BIT_MARK"])
        return timings

    def cases(self):
        low, high = self.constants["DAIKIN_TEMP_MIN"], self.constants["DAIKIN_TEMP_MAX"]
        for mode in ("cool", "heat", "heat_cool"):
            for temperature, fan, swing in itertools.product(range(low, high + 1), self.fan_bytes, SWING_BITS):
                yield mode, temperature, fan, swing
        for mode, fan, swing in itertools.product(("dry", "fan_only"), self.fan_bytes, SWING_BITS):
            yield mode, 25, fan, swing
        yield "off", 25, "auto", "off"


def to_mode2(messages):
    lines = [f"space {MESSAGE_SEPARATOR_US}"]
    for timings in messages:
        lines.extend(("pulse " if index % 2 == 0 else "space ") + str(value) for index, value in enumerate(timings))
        lines.append(f"space {MESSAGE_SEPARATOR_US}")
    return "\n".join(lines) + "\n"


def run_decoder(messages):
    result = subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "sh", "-c", DECODER],
                            input=to_mode2(messages), capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"decoder failed: {result.stderr.strip()}")
    decoded = []
    for block in result.stdout.split("Code length")[1:]:
        kind = re.search(r"Code type\s+-?\d+ \((\w+)\)", block)
        state = re.search(r"State value\s+0x([0-9A-F]+)", block)
        desc = re.search(r"Mesg Desc\.\s+(.*)", block)
        decoded.append((kind.group(1) if kind else "?",
                        bytes.fromhex(state.group(1)) if state else b"",
                        desc.group(1) if desc else ""))
    return decoded


def expected_fields(mode, temperature, fan, swing):
    fields = {
        "Power": "Off" if mode == "off" else "On",
        "Mode": str(IRREMOTE_MODE[mode]),
        "Fan": str(IRREMOTE_FAN[fan]),
        "Swing(H)": "On" if swing in ("horizontal", "both") else "Off",
        "Swing(V)": "On" if swing in ("vertical", "both") else "Off",
    }
    if mode not in ("dry", "fan_only"):
        fields["Temp"] = f"{temperature}C"
    return fields


def parse_desc(desc):
    fields = {}
    for part in desc.split(", "):
        if ": " in part:
            key, value = part.split(": ", 1)
            fields[key] = value.split(" ")[0]
    return fields


def main():
    parser = argparse.ArgumentParser(description="Encode Daikin states exactly as the ESPHome source does, "
                                                 "decode them with IRremoteESP8266.")
    parser.add_argument("--source", choices=("fork", "upstream"), default="fork",
                        help="fork = firmware/components/daikin, upstream = ESPHome inside the container")
    parser.add_argument("--show-failures", type=int, default=10)
    args = parser.parse_args()

    protocol = Protocol(*read_source(args.source))
    all_cases = list(protocol.cases())
    states = [protocol.state(*case) for case in all_cases]
    decoded = run_decoder([protocol.timings(state) for state in states])
    if len(decoded) != len(all_cases):
        sys.exit(f"decoder returned {len(decoded)} results for {len(all_cases)} messages")

    outcome = Counter()
    failures = []
    for case, state, (kind, got_state, desc) in zip(all_cases, states, decoded):
        if kind != "DAIKIN":
            outcome["not recognised as DAIKIN"] += 1
            failures.append((case, f"type {kind}"))
            continue
        if got_state != state:
            outcome["bytes differ"] += 1
            failures.append((case, f"bytes {got_state.hex()}"))
            continue
        got = parse_desc(desc)
        wrong = {key: (value, got.get(key)) for key, value in expected_fields(*case).items() if got.get(key) != value}
        if wrong:
            outcome["meaning differs"] += 1
            failures.append((case, f"{wrong}"))
        else:
            outcome["match"] += 1

    print(f"source   {args.source}, leader bits {protocol.leader_bits}")
    print(f"cases    {len(all_cases)}")
    for label in ("match", "not recognised as DAIKIN", "bytes differ", "meaning differs"):
        print(f"{label:25s} {outcome[label]}")
    for case, reason in failures[:args.show_failures]:
        print(f"  FAIL {case}: {reason}")


if __name__ == "__main__":
    main()
