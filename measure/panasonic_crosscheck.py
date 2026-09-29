import argparse
import csv
import subprocess
import sys
from collections import Counter
from pathlib import Path

from irremote import WSL_DISTRO, decode

TOOL = "~/panasonic_tool"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
PANASONIC_KIND = "PANASONIC_AC"
POWER_WORDS = {"0": "Off", "1": "On"}


def run_tool(mode, text_input=""):
    result = subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "sh", "-c", f"{TOOL} {mode}"],
                            input=text_input, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"panasonic_tool failed: {result.stderr.strip()}. Build it with firmware/tests (see README).")
    return result.stdout.splitlines()


def described(description):
    fields = {}
    for part in description.split(", "):
        if ": " in part:
            key, value = part.split(": ", 1)
            fields[key] = value.split(" ")[0].rstrip("C")
    return fields


def check_sweep(show_failures):
    cases = []
    for line in run_tool("sweep"):
        power, mode, celsius, fan, swing, state_hex, *timings = line.split()
        cases.append(((power, mode, celsius, fan, swing), bytes.fromhex(state_hex), [int(t) for t in timings]))
    decoded = decode([timings for _, _, timings in cases])
    outcome, failures = Counter(), []
    for (fields, state, _), result in zip(cases, decoded):
        power, mode, celsius, fan, swing = fields
        expected_celsius = "27" if mode == "6" else celsius
        expected = {"Power": POWER_WORDS[power], "Mode": mode, "Temp": expected_celsius, "Fan": fan, "Swing(V)": swing}
        got = described(result.description)
        if result.kind != PANASONIC_KIND:
            outcome["not recognised"] += 1
            failures.append((fields, result.kind))
        elif result.state != state:
            outcome["bytes differ"] += 1
            failures.append((fields, result.state.hex()))
        elif any(got.get(key) != value for key, value in expected.items()):
            outcome["meaning differs"] += 1
            failures.append((fields, {key: got.get(key) for key in expected}))
        else:
            outcome["match"] += 1
    print(f"states   {len(cases)}")
    for label in ("match", "not recognised", "bytes differ", "meaning differs"):
        print(f"{label:16s} {outcome[label]}")
    for fields, reason in failures[:show_failures]:
        print(f"  FAIL {fields}: {reason}")


def check_learned(path):
    rows = [row for row in csv.DictReader(path.open(encoding="utf-8")) if PANASONIC_KIND in row["decoded"]]
    if not rows:
        print(f"learned  no Panasonic codes in {path.name}")
        return
    ours = run_tool("decode", "".join(row["raw"] + "\n" for row in rows))
    reference = decode([[int(value) for value in row["raw"].split()] for row in rows])
    for row, mine, theirs in zip(rows, ours, reference):
        state_hex = mine.split()[0]
        verdict = "same bytes" if state_hex == theirs.state.hex() else f"DIFFERENT, IRremoteESP8266 {theirs.state.hex()}"
        print(f"learned  {row['name']:10s} bridge parser {state_hex}  {verdict}")


def main():
    parser = argparse.ArgumentParser(description="Encode every Panasonic RKR state with the firmware code and decode it "
                                                 "with IRremoteESP8266; parse real learned codes both ways.")
    parser.add_argument("--learned", type=Path, help="learned-codes CSV, default: newest in measure/results")
    parser.add_argument("--show-failures", type=int, default=10)
    args = parser.parse_args()
    check_sweep(args.show_failures)
    learned = args.learned or max(RESULTS_DIR.glob("*-learned-codes.csv"), default=None)
    if learned:
        check_learned(learned)


if __name__ == "__main__":
    main()
