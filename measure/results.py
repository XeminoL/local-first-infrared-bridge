import csv
import math
import statistics
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def percentile(sorted_values, fraction):
    return sorted_values[max(0, math.ceil(fraction * len(sorted_values)) - 1)]


def latency_line(values):
    if not values:
        return "latency  no successful samples"
    ordered = sorted(values)
    return (f"latency  median {statistics.median(ordered):.1f} ms, p90 {percentile(ordered, 0.9):.1f} ms, "
            f"min {ordered[0]:.1f} ms, max {ordered[-1]:.1f} ms")


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return value


def save_rows(rows, fields, label):
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{label}.csv"
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: _cell(row.get(field)) for field in fields} for row in rows)
    print(f"saved    {path}")
    return path
