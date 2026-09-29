import argparse
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from bridge import LEARNER_STATUS
from ha_client import connect, require_entities, run_script
from irdb_decode import read_signals
from irremote import UNKNOWN, decode
from learner import calibrate, fetch, fetch_last_capture, forget, learn
from results import save_rows

IRDB_DIR = Path(__file__).resolve().parent / "irdb"
IRDB_FOLDERS = ("acs", "daikin", "tvs")
DEFAULT_FILES = [path for folder in IRDB_FOLDERS for path in sorted((IRDB_DIR / folder).glob("*.ir"))]
SCRATCH_NAME = "fidelity_check"
FIELDS = ["file", "signal", "protocol", "generation", "learned", "status", "decoded", "same_code",
          "mark_bias_us", "space_bias_us", "worst_difference_us", "original", "sent", "captured", "heard"]


def distinct_signals(files, per_file):
    candidates = [(path, name, timings) for path in files for name, timings in read_signals(path)]
    decoded = decode([timings for _, _, timings in candidates])
    picked, seen, per_file_count = [], set(), Counter()
    for (path, name, timings), result in zip(candidates, decoded):
        key = (path.name, result.kind, result.value)
        if result.kind == UNKNOWN or key in seen or per_file_count[path.name] >= per_file:
            continue
        seen.add(key)
        per_file_count[path.name] += 1
        picked.append({"file": path.name, "signal": name, "timings": timings, "reference": result})
    return picked


def timing_error(original, heard):
    if len(original) != len(heard):
        return None, None, None
    marks = [heard[i] - original[i] for i in range(0, len(original), 2)]
    spaces = [heard[i] - original[i] for i in range(1, len(original), 2)]
    worst = max(abs(h - o) for o, h in zip(original, heard))
    return statistics.mean(marks), statistics.mean(spaces) if spaces else 0.0, worst


async def learn_generations(ha, signal, generations):
    rows, previous = [], signal["timings"]
    for generation in range(1, generations + 1):
        try:
            learned, status = await learn(ha, SCRATCH_NAME, previous)
            heard = await fetch(ha, SCRATCH_NAME) if learned else []
            captured = await fetch_last_capture(ha)
        except RuntimeError as error:
            learned, status, heard, captured = False, str(error), [], []
        rows.append({"file": signal["file"], "signal": signal["signal"], "protocol": signal["reference"].summary(),
                     "generation": generation, "learned": learned, "status": status,
                     "original": " ".join(map(str, signal["timings"])), "heard": " ".join(map(str, heard)),
                     "captured": " ".join(map(str, captured)), "sent": " ".join(map(str, previous)),
                     "_heard": heard, "_reference": signal["reference"], "_sent": previous})
        if not learned:
            break
        previous = heard
    return rows


def judge(rows):
    learned_rows = [row for row in rows if row["learned"]]
    for row, result in zip(learned_rows, decode([row["_heard"] for row in learned_rows])):
        row["decoded"] = result.summary()
        row["same_code"] = result.same_code(row["_reference"])
        row["mark_bias_us"], row["space_bias_us"], row["worst_difference_us"] = timing_error(row["_sent"], row["_heard"])
    for row in rows:
        for field in ("decoded", "mark_bias_us", "space_bias_us", "worst_difference_us"):
            row.setdefault(field, None)
        row.setdefault("same_code", False)


def report(rows, generations):
    by_generation = defaultdict(Counter)
    for row in rows:
        by_generation[row["generation"]]["tried"] += 1
        by_generation[row["generation"]]["same"] += row["same_code"]
    signals = len({(row["file"], row["signal"]) for row in rows})
    print(f"signals  {signals} real-remote captures from {len({row['file'] for row in rows})} remotes")
    for generation in range(1, generations + 1):
        counts = by_generation[generation]
        print(f"learned {generation}x  {counts['same']}/{signals} decode to the same code as the original")
    first = [row for row in rows if row["generation"] == 1 and row["mark_bias_us"] is not None]
    if first:
        print(f"timing   marks {statistics.mean(r['mark_bias_us'] for r in first):+.0f} us, "
              f"spaces {statistics.mean(r['space_bias_us'] for r in first):+.0f} us on average, "
              f"worst single pulse {max(r['worst_difference_us'] for r in first)} us")
    for row in rows:
        if not row["same_code"]:
            print(f"  MISS {row['file']} {row['signal']} x{row['generation']}: {row.get('decoded') or row['status']}")


async def main():
    parser = argparse.ArgumentParser(description="Send real-remote captures through the LED, let the bridge learn "
                                                 "them, and check with IRremoteESP8266 that nothing changed.")
    parser.add_argument("files", nargs="*", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--per-file", type=int, default=4)
    parser.add_argument("--generations", type=int, default=2,
                        help="learn the learned code again this many times in total")
    parser.add_argument("--label", default="learn-fidelity")
    parser.add_argument("--skip-calibration", action="store_true")
    args = parser.parse_args()

    signals = distinct_signals(args.files, args.per_file)
    print(f"picked   {len(signals)} signals that IRremoteESP8266 decodes as sent by the real remote")
    async with connect() as ha:
        await require_entities(ha, LEARNER_STATUS)
        if not args.skip_calibration:
            print(f"receiver {await calibrate(ha)}")
        rows = []
        for index, signal in enumerate(signals, 1):
            rows += await learn_generations(ha, signal, args.generations)
            print(f"  {index}/{len(signals)} {signal['file']} {signal['signal']}: {rows[-1]['status']}")
        await forget(ha, SCRATCH_NAME)
    judge(rows)
    save_rows(rows, FIELDS, args.label)
    report(rows, args.generations)


if __name__ == "__main__":
    run_script(main)
