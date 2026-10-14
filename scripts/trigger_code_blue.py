#!/usr/bin/env python3
"""
CLI Tool to trigger or resolve Hospital Code Blue emergency states.

Usage:
    python3 scripts/trigger_code_blue.py CODE_BLUE [unit_name]
    python3 scripts/trigger_code_blue.py RESOLVED
    python3 scripts/trigger_code_blue.py STATUS
"""

import sys
import json
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8080/hospital/emergency"


def post_emergency(status, unit="ICU_Room_1"):
    payload = json.dumps({"status": status, "unit": unit}).encode('utf-8')
    req = urllib.request.Request(API_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("==================================================")
            print(f"Response: {resp.status} {resp.reason}")
            print(json.dumps(data, indent=2))
            print("==================================================")
    except urllib.error.URLError as e:
        print(f"Error connecting to controller at {API_URL}: {e}")
        print("Make sure Ryu controller is running on port 8080.")
        sys.exit(1)


def get_emergency():
    try:
        with urllib.request.urlopen(API_URL) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("==================================================")
            print("Current Emergency Status:")
            print(json.dumps(data, indent=2))
            print("==================================================")
    except urllib.error.URLError as e:
        print(f"Error connecting to controller at {API_URL}: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 scripts/trigger_code_blue.py CODE_BLUE [unit_name]")
        print("  python3 scripts/trigger_code_blue.py RESOLVED")
        print("  python3 scripts/trigger_code_blue.py STATUS")
        sys.exit(1)

    cmd = sys.argv[1].upper()
    unit = sys.argv[2] if len(sys.argv) > 2 else "ICU_Room_1"

    if cmd == "CODE_BLUE":
        print(f"[*] Sending CODE_BLUE emergency alert for unit: {unit}...")
        post_emergency("CODE_BLUE", unit)
    elif cmd == "RESOLVED":
        print("[*] Sending emergency RESOLVED notification...")
        post_emergency("RESOLVED", unit)
    elif cmd == "STATUS":
        get_emergency()
    else:
        print(f"Unknown command '{cmd}'. Use CODE_BLUE, RESOLVED, or STATUS.")
        sys.exit(1)


if __name__ == "__main__":
    main()
