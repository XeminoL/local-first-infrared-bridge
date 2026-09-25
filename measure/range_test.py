import argparse
import asyncio
import csv
import statistics
from datetime import datetime

import climate_sweep
import loopback
from bridge import REMOTE_CLIMATE, TEST_BUTTON, TEST_CODE_EVENT, VIRTUAL_CLIMATE
from ha_client import connect, require_entities, run_script
from results import RESULTS_DIR

SUMMARY_FILE = RESULTS_DIR / "range-summary.csv"
FIELDS = ["time", "distance_cm", "setup", "nec_ok", "nec_total", "nec_median_ms",
          "daikin_ok", "daikin_total", "daikin_median_ms", "note"]


def median_or_blank(values):
    return round(statistics.median(values), 1) if values else ""


async def measure(ha, nec_trials, daikin_steps):
    nec_rows = await loopback.run_trials(ha, nec_trials, loopback.DEFAULT_GAP_S) if nec_trials else []
    daikin_rows = []
    if daikin_steps:
        await climate_sweep.sync_to_base(ha)
        daikin_rows = await climate_sweep.run_steps(ha, 1, climate_sweep.DEFAULT_GAP_S, daikin_steps)
    nec_ok = [row["latency_ms"] for row in nec_rows if row["outcome"] == "correct"]
    daikin_ok = [row["latency_ms"] for row in daikin_rows if row["outcome"] == "match"]
    return {
        "nec_ok": len(nec_ok), "nec_total": len(nec_rows), "nec_median_ms": median_or_blank(nec_ok),
        "daikin_ok": len(daikin_ok), "daikin_total": len(daikin_rows), "daikin_median_ms": median_or_blank(daikin_ok),
    }


def append_summary(row):
    RESULTS_DIR.mkdir(exist_ok=True)
    new_file = not SUMMARY_FILE.exists()
    with SUMMARY_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def print_table():
    with SUMMARY_FILE.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    print()
    print(f"{'distance':>9} {'setup':10} {'NEC':>9} {'NEC ms':>8} {'Daikin':>8} {'Daikin ms':>10}  note")
    for row in rows:
        print(f"{row['distance_cm']:>7}cm {row['setup']:10} {row['nec_ok']:>4}/{row['nec_total']:<4} "
              f"{row['nec_median_ms']:>8} {row['daikin_ok']:>3}/{row['daikin_total']:<4} "
              f"{row['daikin_median_ms']:>10}  {row['note']}")


async def main():
    parser = argparse.ArgumentParser(description="Range test by mirror: LED and receiver side by side facing a "
                                                 "mirror at a given distance. Run once per distance and setup.")
    parser.add_argument("--distance-cm", type=int, required=True, help="board to mirror distance, path is twice this")
    parser.add_argument("--setup", choices=("mirror", "covered"), required=True,
                        help="covered = mirror blocked, a control for light leaking straight from LED to receiver")
    parser.add_argument("--nec", type=int, default=30)
    parser.add_argument("--daikin", type=int, default=10)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    async with connect() as ha:
        await require_entities(ha, TEST_BUTTON, TEST_CODE_EVENT, REMOTE_CLIMATE, VIRTUAL_CLIMATE)
        result = await measure(ha, args.nec, args.daikin)

    append_summary({"time": datetime.now().strftime("%H:%M:%S"), "distance_cm": args.distance_cm,
                    "setup": args.setup, "note": args.note, **result})
    print_table()


if __name__ == "__main__":
    run_script(main)
