import argparse
import asyncio
import time
from collections import Counter, defaultdict

from bridge import REMOTE_CLIMATE, VIRTUAL_CLIMATE
from climate_state import apply_state, command, compared_fields, matches, wait_for_virtual
from ha_client import connect, require_entities, run_script
from results import latency_line, save_rows

REPLY_TIMEOUT_S = 3.0
DEFAULT_GAP_S = 0.8
DEFAULT_ROUNDS = 2
BASE_STATE = {"hvac_mode": "cool", "temperature": 24, "fan_mode": "auto", "swing_mode": "off"}
TEMPERATURE_PATH = list(range(25, 31)) + list(range(29, 9, -1)) + list(range(11, 25))
MODE_PATH = ("heat", "heat_cool", "dry", "fan_only", "off", "cool")
FAN_PATH = ("quiet", "low", "medium", "high", "auto")
SWING_PATH = ("vertical", "horizontal", "both", "off")


def one_round():
    return ([("temperature", value) for value in TEMPERATURE_PATH]
            + [("hvac_mode", value) for value in MODE_PATH]
            + [("fan_mode", value) for value in FAN_PATH]
            + [("swing_mode", value) for value in SWING_PATH])


async def sync_to_base(ha):
    seen = await apply_state(ha, BASE_STATE)
    return matches(BASE_STATE, seen, compared_fields(BASE_STATE)), seen


async def run_steps(ha, rounds, gap_s, limit=0):
    expected = dict(BASE_STATE)
    rows = []
    steps = (one_round() * rounds)[:limit or None]
    for index, (field, value) in enumerate(steps, 1):
        expected[field] = value
        ha.drain_events()
        started = time.perf_counter()
        await command(ha, field, value)
        outcome, received_at, seen = await wait_for_virtual(ha, expected, started + REPLY_TIMEOUT_S,
                                                            compared_fields(expected))
        latency_ms = (received_at - started) * 1000 if received_at else None
        rows.append({"step": index, "field": field, "value": value, "outcome": outcome,
                     "latency_ms": latency_ms, "seen": seen})
        shown = f"{latency_ms:7.1f} ms" if latency_ms is not None else "      -   "
        print(f"{index:4d}/{len(steps)}  {field:11s} {str(value):10s} {outcome:7s} {shown}")
        await asyncio.sleep(gap_s)
    return rows


def summarize(rows):
    total = len(rows)
    counts = Counter(row["outcome"] for row in rows)
    per_field = defaultdict(Counter)
    for row in rows:
        per_field[row["field"]][row["outcome"]] += 1
    print()
    print(f"steps    {total}")
    print(f"match    {counts['match']}  ({counts['match'] / total:.1%})")
    print(f"wrong    {counts['wrong']}")
    print(f"missed   {counts['missed']}")
    for field, tally in per_field.items():
        print(f"  {field:11s} {tally['match']}/{sum(tally.values())}")
    print(latency_line([row["latency_ms"] for row in rows if row["outcome"] == "match"]))
    for row in rows:
        if row["outcome"] != "match":
            print(f"  FAIL step {row['step']} {row['field']}={row['value']}: {row['outcome']}, virtual saw {row['seen']}")


async def main():
    parser = argparse.ArgumentParser(description="Drive the Daikin Remote entity one field at a time and check "
                                                 "the listen-only Virtual Daikin decodes the same state.")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--gap", type=float, default=DEFAULT_GAP_S, help="seconds between steps")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many steps (0 = all)")
    parser.add_argument("--label", default="climate-sweep")
    args = parser.parse_args()

    async with connect() as ha:
        await require_entities(ha, REMOTE_CLIMATE, VIRTUAL_CLIMATE)
        in_sync, seen = await sync_to_base(ha)
        print(f"start    base {BASE_STATE}, virtual {'in sync' if in_sync else f'NOT in sync: {seen}'}")
        rows = await run_steps(ha, args.rounds, args.gap, args.limit)

    summarize(rows)
    save_rows(rows, ["step", "field", "value", "outcome", "latency_ms", "seen"], args.label)


if __name__ == "__main__":
    run_script(main)
