import argparse
import asyncio
import statistics
import time

from bridge import ECHO_EVENT, REMOTE_CLIMATE, UNCONFIRMED_EVENT_TYPE
from ha_client import connect, require_entities, run_script
from prompt import wait_for_enter
from results import save_rows

BASELINE_COMMANDS = 5
OUTAGE_COMMANDS = 10
COMMAND_GAP_S = 4.0
LISTEN_S = 3.5
RECOVERY_GIVE_UP_S = 120.0
ALTERNATING_TEMPERATURES = (24, 25)
FIELDS = ["phase", "t_s", "accepted", "echo_ms", "alert_ms"]


def milliseconds_since(start, moment):
    return round((moment - start) * 1000) if moment else None


async def send_and_listen(ha, sequence_number):
    ha.drain_events()
    sent_at = time.perf_counter()
    try:
        temperature = ALTERNATING_TEMPERATURES[sequence_number % len(ALTERNATING_TEMPERATURES)]
        await ha.call("climate", "set_temperature", REMOTE_CLIMATE, temperature=temperature)
        accepted = True
    except (ConnectionError, RuntimeError):
        accepted = False
    echo_at = alert_at = None
    deadline = sent_at + LISTEN_S
    while time.perf_counter() < deadline:
        try:
            received_at, event = await asyncio.wait_for(ha.events.get(), deadline - time.perf_counter())
        except asyncio.TimeoutError:
            break
        if event.get("event_type") == UNCONFIRMED_EVENT_TYPE:
            alert_at = alert_at or received_at
        new_state = (event.get("data") or {}).get("new_state") or {}
        if new_state.get("entity_id") == ECHO_EVENT:
            echo_at = echo_at or received_at
    return {"accepted": accepted, "echo_ms": milliseconds_since(sent_at, echo_at),
            "alert_ms": milliseconds_since(sent_at, alert_at)}


async def run_phase(ha, phase, count, rows, origin):
    for index in range(count):
        result = await send_and_listen(ha, len(rows))
        rows.append({"phase": phase, "t_s": time.perf_counter() - origin, **result})
        print(f"  {phase:9s} {index + 1:2d}/{count}  accepted={result['accepted']!s:5s} "
              f"echo={result['echo_ms']} ms  alert={result['alert_ms']} ms")
        await asyncio.sleep(COMMAND_GAP_S - LISTEN_S)


async def run_recovery(ha, rows, origin, restored_at):
    while time.perf_counter() - restored_at < RECOVERY_GIVE_UP_S:
        result = await send_and_listen(ha, len(rows))
        rows.append({"phase": "recovery", "t_s": time.perf_counter() - origin, **result})
        print(f"  recovery  t={time.perf_counter() - restored_at:5.1f}s  echo={result['echo_ms']} ms  "
              f"alert={result['alert_ms']} ms")
        if result["echo_ms"] is not None:
            return time.perf_counter() - restored_at
        await asyncio.sleep(COMMAND_GAP_S - LISTEN_S)
    return None


def summarize(rows, recovered_s):
    baseline = [row for row in rows if row["phase"] == "baseline"]
    outage = [row for row in rows if row["phase"] == "outage"]
    alerts = [row["alert_ms"] for row in outage if row["alert_ms"] is not None]
    print()
    print(f"baseline  confirmed {sum(r['echo_ms'] is not None for r in baseline)}/{len(baseline)}, "
          f"false alerts {sum(r['alert_ms'] is not None for r in baseline)}")
    print(f"outage    accepted by HA {sum(r['accepted'] for r in outage)}/{len(outage)}, "
          f"echo {sum(r['echo_ms'] is not None for r in outage)}, alerted {len(alerts)}/{len(outage)}")
    if alerts:
        print(f"          alert delay median {statistics.median(alerts)} ms, max {max(alerts)} ms")
    print(f"recovery  confirmed again after {recovered_s:.1f} s" if recovered_s else "recovery  not confirmed")


async def main():
    argparse.ArgumentParser(description="Check that every lost IR command raises an alert within seconds, "
                                        "using the receiver's echo as confirmation.").parse_args()
    rows = []
    origin = time.perf_counter()
    async with connect() as ha:
        await require_entities(ha, REMOTE_CLIMATE, ECHO_EVENT)
        await ha.request({"type": "subscribe_events", "event_type": UNCONFIRMED_EVENT_TYPE})
        print("baseline: ESP32 plugged in, every command should be confirmed")
        await run_phase(ha, "baseline", BASELINE_COMMANDS, rows, origin)
        await wait_for_enter("Unplug the ESP32 USB cable now, then press Enter.")
        await run_phase(ha, "outage", OUTAGE_COMMANDS, rows, origin)
        restored_at = await wait_for_enter("Plug the ESP32 USB cable back in, then press Enter.")
        recovered_s = await run_recovery(ha, rows, origin, restored_at)
    summarize(rows, recovered_s)
    save_rows(rows, FIELDS, "confirmation")


if __name__ == "__main__":
    run_script(main)
