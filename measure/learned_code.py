import argparse

from bridge import SAVED_CODES
from ha_client import connect, require_entities, run_script
from irremote import run_decoder
from learner import fetch
from results import save_rows

FIELDS = ["name", "timings", "length_ms", "decoded", "description", "raw"]


async def main():
    parser = argparse.ArgumentParser(description="Read codes learned by the bridge and let IRremoteESP8266 "
                                                 "name the protocol.")
    parser.add_argument("names", nargs="*", help="code names, default: every saved code")
    parser.add_argument("--save", action="store_true", help="also write the timings to measure/results")
    args = parser.parse_args()

    async with connect() as ha:
        states = await require_entities(ha, SAVED_CODES)
        names = args.names or [name.strip() for name in states[SAVED_CODES]["state"].split(",") if name.strip()]
        codes = {name: await fetch(ha, name) for name in names}

    missing = [name for name, timings in codes.items() if not timings]
    found = {name: timings for name, timings in codes.items() if timings}
    rows = []
    for name, timings in found.items():
        results = run_decoder([timings])
        decoded = "; ".join(result.summary() for result in results) or "UNKNOWN"
        description = next((result.description for result in results if result.description), "")
        rows.append({"name": name, "timings": len(timings), "length_ms": sum(timings) / 1000,
                     "decoded": decoded, "description": description, "raw": " ".join(map(str, timings))})
        print(f"{name:24s} {len(timings):4d} timings {sum(timings) / 1000:7.1f} ms  {decoded}")
        if description:
            print(f"{'':24s} {description}")
    for name in missing:
        print(f"{name:24s} not saved on the bridge")
    if args.save and rows:
        save_rows(rows, FIELDS, "learned-codes")


if __name__ == "__main__":
    run_script(main)
