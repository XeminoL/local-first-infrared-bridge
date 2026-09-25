import argparse
import asyncio
import subprocess
import time

import aiohttp

from bridge import TEST_BUTTON
from ha_client import connect, run_script
from loopback import press_once
from prompt import wait_for_enter
from results import save_rows

PROBE_INTERVAL_S = 1.0
REPLY_TIMEOUT_S = 1.5
HOLD_AFTER_DETECTION_S = 15.0
MAX_OUTAGE_S = 130.0
GIVE_UP_S = 320.0
WSL_DISTRO = "Ubuntu"
HA_CONTAINER = "homeassistant"
FIELDS = ["t_s", "phase", "entity_state", "call_accepted", "ir_ok", "error"]
PROMPTS = {
    "usb": ("Unplug the ESP32 USB cable now, then press Enter.",
            "Plug the ESP32 USB cable back in, then press Enter."),
    "wifi": ("Turn OFF the phone hotspot now, then press Enter.",
             "Turn the phone hotspot back ON, then press Enter."),
}


async def probe(ha, origin, phase):
    try:
        pressed_at, outcome, _ = await press_once(ha, REPLY_TIMEOUT_S)
        accepted, ir_ok, error = True, outcome == "correct", ""
    except (ConnectionError, RuntimeError) as failure:
        pressed_at, accepted, ir_ok, error = time.perf_counter(), False, False, str(failure)[:80]
    state = (await ha.states()).get(TEST_BUTTON, {}).get("state", "missing") if not ha.closed else "no-connection"
    row = {"t_s": pressed_at - origin, "phase": phase, "entity_state": state,
           "call_accepted": accepted, "ir_ok": ir_ok, "error": error}
    print(f"  t={pressed_at - origin:6.1f}s  state={state:11s} accepted={accepted!s:5s} ir_ok={ir_ok!s:5s} {error}")
    return row


def elapsed(start, end):
    return end - start if start is not None and end is not None else None


async def run_manual(ha, scenario):
    fault_prompt, restore_prompt = PROMPTS[scenario]
    fault_at = await wait_for_enter(fault_prompt)
    rows = []
    prompted_at = enter_task = None
    unavailable_at = available_at = recovered_at = None
    while time.perf_counter() - fault_at < GIVE_UP_S:
        row = await probe(ha, fault_at, "restoring" if prompted_at else "fault")
        rows.append(row)
        now = time.perf_counter()
        if row["entity_state"] == "unavailable" and unavailable_at is None:
            unavailable_at = now
        if prompted_at and row["entity_state"] != "unavailable" and available_at is None:
            available_at = now
        if prompted_at and row["ir_ok"] and recovered_at is None:
            recovered_at = now
        if recovered_at and enter_task.done():
            break
        held_long_enough = unavailable_at is not None and now - unavailable_at >= HOLD_AFTER_DETECTION_S
        if prompted_at is None and (held_long_enough or now - fault_at >= MAX_OUTAGE_S):
            prompted_at = time.perf_counter()
            enter_task = asyncio.create_task(wait_for_enter(restore_prompt))
        await asyncio.sleep(PROBE_INTERVAL_S)
    enter_at = await enter_task if enter_task else None
    silently_lost = sum(1 for row in rows if row["phase"] == "fault" and row["call_accepted"] and not row["ir_ok"])
    return rows, {
        "outage_until_prompt_s": elapsed(fault_at, prompted_at),
        "detect_s": elapsed(fault_at, unavailable_at),
        "silently_lost_presses": silently_lost,
        "available_after_prompt_s": elapsed(prompted_at, available_at),
        "working_after_prompt_s": elapsed(prompted_at, recovered_at),
        "working_minus_enter_s": elapsed(enter_at, recovered_at),
    }


async def run_ha_restart():
    print("\n>>> Restarting the Home Assistant container.")
    restart_at = time.perf_counter()
    subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "docker", "restart", HA_CONTAINER], capture_output=True)
    command_done_at = time.perf_counter()
    rows = []
    reconnected_at = recovered_at = None
    while recovered_at is None and time.perf_counter() - restart_at < GIVE_UP_S:
        try:
            async with connect() as ha:
                reconnected_at = reconnected_at or time.perf_counter()
                while not ha.closed and time.perf_counter() - restart_at < GIVE_UP_S:
                    row = await probe(ha, restart_at, "restarting")
                    rows.append(row)
                    if row["ir_ok"]:
                        recovered_at = time.perf_counter()
                        break
                    await asyncio.sleep(PROBE_INTERVAL_S)
        except (OSError, RuntimeError, aiohttp.ClientError) as failure:
            rows.append({"t_s": time.perf_counter() - restart_at, "phase": "restarting",
                         "entity_state": "no-connection", "call_accepted": False, "ir_ok": False,
                         "error": type(failure).__name__})
            await asyncio.sleep(PROBE_INTERVAL_S)
    return rows, {
        "docker_restart_command_s": elapsed(restart_at, command_done_at),
        "websocket_back_s": elapsed(restart_at, reconnected_at),
        "working_after_restart_s": elapsed(restart_at, recovered_at),
    }


def report(summary, scenario):
    print()
    print(f"scenario {scenario}")
    for key, value in summary.items():
        shown = "-" if value is None else value if isinstance(value, int) else f"{value:.1f}"
        print(f"{key:28s} {shown}")


async def main():
    parser = argparse.ArgumentParser(description="Break one thing, keep pressing the loopback button, "
                                                 "and time how long until it works again.")
    parser.add_argument("scenario", choices=("usb", "wifi", "ha"))
    args = parser.parse_args()
    if args.scenario == "ha":
        rows, summary = await run_ha_restart()
    else:
        async with connect() as ha:
            _, outcome, _ = await press_once(ha, REPLY_TIMEOUT_S)
            if outcome != "correct":
                raise SystemExit(f"Loopback does not work before the test ({outcome}). Fix that first.")
            rows, summary = await run_manual(ha, args.scenario)
    report(summary, args.scenario)
    save_rows(rows, FIELDS, f"recovery-{args.scenario}")


if __name__ == "__main__":
    run_script(main)
