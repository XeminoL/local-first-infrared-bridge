import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from results import save_rows

WEB_USER = "admin"
REQUEST_TIMEOUT_S = 5
READINGS = {"uptime_s": "sensor/Uptime", "heap_free": "sensor/Heap free",
            "heap_largest_block": "sensor/Heap largest block", "wifi_dbm": "sensor/WiFi signal"}
FIELDS = ["time", "reachable", *READINGS, "rebooted"]


def opener(address, password):
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, f"http://{address}/", WEB_USER, password)
    return urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(manager))


def read(web, address, path):
    url = f"http://{address}/{urllib.parse.quote(path)}"
    with web.open(url, timeout=REQUEST_TIMEOUT_S) as response:
        return json.load(response).get("value")


def sample(web, address):
    row = {"time": datetime.now().strftime("%H:%M:%S")}
    try:
        for field, path in READINGS.items():
            row[field] = read(web, address, path)
        row["reachable"] = True
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
        row["reachable"] = False
    return row


def summary(rows):
    reached = [row for row in rows if row["reachable"]]
    heap = [row["heap_free"] for row in reached if row.get("heap_free") is not None]
    print(f"samples  {len(rows)}, reachable {len(reached)}, reboots {sum(bool(row.get('rebooted')) for row in rows)}")
    if heap:
        print(f"heap     first {heap[0]:.0f} B, last {heap[-1]:.0f} B, lowest {min(heap):.0f} B")
    signal = [row["wifi_dbm"] for row in reached if row.get("wifi_dbm") is not None]
    if signal:
        print(f"wifi     {min(signal):.0f} to {max(signal):.0f} dBm")


def main():
    parser = argparse.ArgumentParser(description="Poll the bridge's own web server and record uptime, memory and WiFi.")
    parser.add_argument("--address", required=True)
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--every", type=float, default=30, help="seconds between samples")
    args = parser.parse_args()
    password = os.environ.get("WEB_PASSWORD")
    if not password:
        sys.exit("Set WEB_PASSWORD to the web_password from firmware/secrets.yaml.")

    web = opener(args.address, password)
    rows, last_uptime = [], None
    deadline = time.monotonic() + args.minutes * 60
    try:
        while time.monotonic() < deadline:
            row = sample(web, args.address)
            uptime = row.get("uptime_s")
            row["rebooted"] = uptime is not None and last_uptime is not None and uptime < last_uptime
            if uptime is not None:
                last_uptime = uptime
            rows.append(row)
            print(f"{row['time']} {'up' if row['reachable'] else 'NO ANSWER'} {row.get('uptime_s')} s, "
                  f"heap {row.get('heap_free')}, wifi {row.get('wifi_dbm')}{'  REBOOTED' if row['rebooted'] else ''}",
                  flush=True)
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass
    save_rows(rows, FIELDS, "soak")
    summary(rows)


if __name__ == "__main__":
    main()
