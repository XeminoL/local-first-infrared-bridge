import argparse
import asyncio
import time

from bridge import TEST_BUTTON, TEST_CODE_EVENT
from ha_client import connect, require_entities, run_script
from results import latency_line, save_rows

DEFAULT_TRIALS = 100
DEFAULT_GAP_S = 0.5
REPLY_TIMEOUT_S = 2.0
OUTCOMES = ("correct", "wrong", "missed")


async def wait_for_test_code(ha, deadline):
    while True:
        reply = await ha.next_state(TEST_CODE_EVENT, deadline)
        if reply is None:
            return None
        received_at, new_state = reply
        event_type = new_state.get("attributes", {}).get("event_type")
        if event_type:
            return received_at, event_type


async def press_once(ha, timeout_s=REPLY_TIMEOUT_S):
    ha.drain_events()
    pressed_at = time.perf_counter()
    await ha.call("button", "press", TEST_BUTTON)
    reply = await wait_for_test_code(ha, pressed_at + timeout_s)
    if reply is None:
        return pressed_at, "missed", None
    received_at, outcome = reply
    return pressed_at, outcome, (received_at - pressed_at) * 1000


async def run_trials(ha, trials, gap_s):
    rows = []
    for trial in range(1, trials + 1):
        _, outcome, latency_ms = await press_once(ha)
        rows.append({"trial": trial, "outcome": outcome, "latency_ms": latency_ms})
        shown = f"{latency_ms:7.1f} ms" if latency_ms is not None else "      -   "
        print(f"{trial:4d}/{trials}  {outcome:7s} {shown}")
        await asyncio.sleep(gap_s)
    return rows


def summarize(rows):
    total = len(rows)
    counts = {outcome: sum(row["outcome"] == outcome for row in rows) for outcome in OUTCOMES}
    print()
    print(f"trials   {total}")
    print(f"correct  {counts['correct']}  ({counts['correct'] / total:.1%})")
    print(f"wrong    {counts['wrong']}")
    print(f"missed   {counts['missed']}")
    print(latency_line([row["latency_ms"] for row in rows if row["outcome"] == "correct"]))


async def main():
    parser = argparse.ArgumentParser(description="Press the IR Bridge test button and time the loopback reply.")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--gap", type=float, default=DEFAULT_GAP_S, help="seconds between trials")
    parser.add_argument("--label", default="loopback")
    args = parser.parse_args()

    async with connect() as ha:
        await require_entities(ha, TEST_BUTTON, TEST_CODE_EVENT)
        rows = await run_trials(ha, args.trials, args.gap)

    summarize(rows)
    save_rows(rows, ["trial", "outcome", "latency_ms"], args.label)


if __name__ == "__main__":
    run_script(main)
