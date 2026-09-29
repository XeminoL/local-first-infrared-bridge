import re
import subprocess
import sys
from dataclasses import dataclass

WSL_DISTRO = "Ubuntu"
DECODER = "~/irremote/tools/mode2_decode_long"
MESSAGE_SEPARATOR_US = 65535
UNKNOWN = "UNKNOWN"
SEPARATOR_VALUE = 0xE51A3CC3
NEC_BITS = 32
NEC_HEADER_MARK, NEC_HEADER_SPACE = 9000, 4500
NEC_BIT_MARK, NEC_ONE_SPACE, NEC_ZERO_SPACE = 560, 1690, 560


@dataclass
class Decoded:
    kind: str
    bits: int
    value: str
    state: bytes
    description: str

    def same_code(self, other):
        return self.kind != UNKNOWN and (self.kind, self.bits, self.value) == (other.kind, other.bits, other.value)

    def summary(self):
        if self.kind == UNKNOWN:
            return UNKNOWN
        return f"{self.kind} {self.bits} bits {self.value}"


def to_mode2(messages):
    lines = [f"space {MESSAGE_SEPARATOR_US}"]
    for timings in messages:
        lines.extend(("pulse " if index % 2 == 0 else "space ") + str(abs(value)) for index, value in enumerate(timings))
        lines.append(f"space {MESSAGE_SEPARATOR_US}")
    return "\n".join(lines) + "\n"


def parse_block(block):
    kind = re.search(r"Code type\s+-?\d+ \((\w+)\)", block)
    bits = re.search(r"Code bits\s+(\d+)", block)
    state = re.search(r"State value\s+0x([0-9A-F]+)", block)
    value = re.search(r"Code value\s+(0x[0-9a-f]+)", block)
    description = re.search(r"Mesg Desc\.\s+(.*)", block)
    state_bytes = bytes.fromhex(state.group(1)) if state else b""
    return Decoded(
        kind=kind.group(1) if kind else UNKNOWN,
        bits=int(bits.group(1)) if bits else 0,
        value=state_bytes.hex() if state else (value.group(1) if value else ""),
        state=state_bytes,
        description=description.group(1).strip() if description else "",
    )


def nec_timings(value):
    timings = [NEC_HEADER_MARK, NEC_HEADER_SPACE]
    for bit in range(NEC_BITS):
        timings += [NEC_BIT_MARK, NEC_ONE_SPACE if (value >> (NEC_BITS - 1 - bit)) & 1 else NEC_ZERO_SPACE]
    return timings + [NEC_BIT_MARK]


def run_decoder(messages):
    result = subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "sh", "-c", DECODER],
                            input=to_mode2(messages), capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"IRremoteESP8266 decoder failed: {result.stderr.strip()}. Build it with build_irremote_decoder.sh")
    return [parse_block(block) for block in result.stdout.split("Code length")[1:]]


def decode_each(messages):
    separator = nec_timings(SEPARATOR_VALUE)
    stream = [separator]
    for timings in messages:
        stream += [timings, separator]
    groups, current = [], None
    for result in run_decoder(stream):
        if result.kind == "NEC" and result.value == hex(SEPARATOR_VALUE):
            if current is not None:
                groups.append(current)
            current = []
        elif current is not None:
            current.append(result)
    if len(groups) != len(messages):
        sys.exit(f"decoder output could not be matched to the messages ({len(groups)} groups, {len(messages)} messages)")
    return groups


def decode(messages):
    return [group[0] if group else Decoded(UNKNOWN, 0, "", b"", "") for group in decode_each(messages)]
