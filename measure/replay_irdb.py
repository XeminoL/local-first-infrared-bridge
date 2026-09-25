import argparse
import asyncio
import time
from collections import Counter
from pathlib import Path

from bridge import REMOTE_CLIMATE, SEND_RAW_DOMAIN, SEND_RAW_SERVICE, VIRTUAL_CLIMATE
from climate_state import TEMPERATURE_MODES, apply_state, matches, virtual_state, wait_for_virtual
from ha_client import connect, require_entities, run_script
from irdb_decode import checksum_ok, decode_frame, read_signals, split_frames
from results import save_rows

DEFAULT_FILES = sorted((Path(__file__).resolve().parent / "irdb" / "daikin").glob("*.ir"))
REPLY_TIMEOUT_S = 3.0
GAP_S = 0.8

STATE_FRAME_PREFIX = bytes([0x11, 0xDA, 0x27, 0x00, 0x00])
STATE_FRAME_SIZE = 19
MODE_BYTE, TEMPERATURE_BYTE, FAN_BYTE, SWING_BYTE = 5, 6, 8, 9
POWER_ON = 0x01
HIGH_NIBBLE, LOW_NIBBLE = 0xF0, 0x0F
MODES = {0x30: "cool", 0x20: "dry", 0x40: "heat", 0x00: "heat_cool", 0x60: "fan_only"}
FANS = {0x30: "low", 0x40: "low", 0x50: "medium", 0x60: "high", 0x70: "high", 0xA0: "auto", 0xB0: "quiet"}
SWINGS = {(True, True): "both", (True, False): "vertical", (False, True): "horizontal", (False, False): "off"}
SENTINELS = (
    {"hvac_mode": "heat", "temperature": 10, "fan_mode": "quiet", "swing_mode": "both"},
    {"hvac_mode": "cool", "temperature": 30, "fan_mode": "high", "swing_mode": "horizontal"},
)


def state_frame(timings):
    frames = [decode_frame(frame) for frame in split_frames(timings)]
    candidates = [f for f in frames if f and len(f) == STATE_FRAME_SIZE and f.startswith(STATE_FRAME_PREFIX)]
    return candidates[-1] if candidates else None


def meant_state(frame):
    if not frame or not checksum_ok(frame):
        return None
    mode, fan = frame[MODE_BYTE], frame[FAN_BYTE]
    state = {
        "fan_mode": FANS.get(fan & HIGH_NIBBLE),
        "swing_mode": SWINGS[(bool(fan & LOW_NIBBLE), bool(frame[SWING_BYTE] & LOW_NIBBLE))],
        "hvac_mode": MODES.get(mode & HIGH_NIBBLE) if mode & POWER_ON else "off",
    }
    if state["hvac_mode"] in TEMPERATURE_MODES:
        state["temperature"] = frame[TEMPERATURE_BYTE] * 0.5
    return state


def signed(timings):
    return [value if index % 2 == 0 else -value for index, value in enumerate(timings)]


def collect(files):
    signals, skipped = [], Counter()
    for path in files:
        for name, timings in read_signals(path):
            expected = meant_state(state_frame(timings))
            if expected is None or None in expected.values():
                skipped[path.name] += 1
            else:
                signals.append((path.name, name, timings, expected))
    return signals, skipped


async def make_change_visible(ha, expected):
    before = await virtual_state(ha)
    if not matches(expected, before):
        return True
    sentinel = next(state for state in SENTINELS if not matches(expected, state))
    return matches(sentinel, await apply_state(ha, sentinel))


async def replay(ha, signals):
    rows = []
    for index, (file_name, name, timings, expected) in enumerate(signals, 1):
        if not await make_change_visible(ha, expected):
            outcome, seen = "sentinel-failed", await virtual_state(ha)
        else:
            ha.drain_events()
            deadline = time.perf_counter() + REPLY_TIMEOUT_S
            await ha.call(SEND_RAW_DOMAIN, SEND_RAW_SERVICE, timings=signed(timings))
            outcome, _, seen = await wait_for_virtual(ha, expected, deadline)
            await asyncio.sleep(GAP_S)
        rows.append({"file": file_name, "signal": name, "outcome": outcome, "expected": expected, "seen": seen})
        print(f"{index:3d}/{len(signals)}  {file_name:28s} {name:14s} {outcome}")
    return rows


def summarize(rows, skipped, label):
    by_file = {}
    for row in rows:
        by_file.setdefault(row["file"], Counter())[row["outcome"]] += 1
    total = Counter(row["outcome"] for row in rows)
    print()
    print(f"firmware {label}")
    print(f"signals  {len(rows)}  match {total['match']}  wrong {total['wrong']}  missed {total['missed']}  "
          f"sentinel-failed {total['sentinel-failed']}")
    for name, tally in by_file.items():
        print(f"  {name:28s} {tally['match']}/{sum(tally.values())}")
    for name, count in skipped.items():
        print(f"  skipped {name}: {count} signals without a Daikin state frame")
    for row in rows:
        if row["outcome"] != "match":
            print(f"  FAIL {row['file']} {row['signal']}: {row['outcome']}, expected {row['expected']}, saw {row['seen']}")


async def main():
    parser = argparse.ArgumentParser(description="Replay real Daikin remote captures through the IR LED and check "
                                                 "the listen-only Virtual Daikin decodes the state the remote meant.")
    parser.add_argument("files", nargs="*", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--label", required=True, help="which firmware is flashed, e.g. fork or upstream")
    args = parser.parse_args()

    signals, skipped = collect(args.files)
    async with connect() as ha:
        await require_entities(ha, REMOTE_CLIMATE, VIRTUAL_CLIMATE)
        if SEND_RAW_SERVICE not in await ha.services(SEND_RAW_DOMAIN):
            raise SystemExit(f"{SEND_RAW_DOMAIN}.{SEND_RAW_SERVICE} not found. Is the send_raw action flashed?")
        rows = await replay(ha, signals)

    summarize(rows, skipped, args.label)
    save_rows(rows, ["file", "signal", "outcome", "expected", "seen"], f"replay-{args.label}")


if __name__ == "__main__":
    run_script(main)
