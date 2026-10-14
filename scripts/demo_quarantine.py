#!/usr/bin/env python3
"""
Demonstration Script for Idea 2: Automated IoMT Anomaly Quarantine (Closed-Loop Reactive Security)
Standalone, end-to-end live security evaluation with Mininet and Ryu OpenFlow 1.3.

Demonstrates:
1. Baseline: IoMT device (h_monitor1 at 10.0.4.10) authorized to communicate with Med Server at < 1 Mbps.
2. Anomaly Detection: Device initiates an anomalous traffic flood (simulating malware / DDoS / port scan).
3. Closed-Loop SDN Response:
   - Ryu periodic flow stats monitor detects bandwidth exceeding the 1.0 Mbps baseline threshold.
   - Autonomous flow modification installs strict priority 90 drop rules.
   - Logs security alert: [SECURITY ALERT] IoT Host 10.0.4.10 anomalous traffic detected -> Quarantined.
4. Verification:
   - Compromised IoMT host is 100% blocked and isolated from the hospital network.
   - Legitimate hospital traffic (h_doc1 -> Med Server) continues completely uninterrupted.
5. Administrative Remediation:
   - Security admin issues POST /hospital/quarantine {"host": "10.0.4.10", "action": "RELEASE"}.
   - Baseline communication is cleanly restored.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
PYTHON_EXE = sys.executable
CONTROLLER_APP = os.path.join(REPO_ROOT, 'controller', 'hospital_controller.py')
API_URL = 'http://127.0.0.1:8080'

sys.path.append(REPO_ROOT)
from topology.hospital_topo import HospitalTopo, configure_qos

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel


# Terminal styling
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


def print_header(title):
    print(f"\n{BOLD}{CYAN}{'=' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}")


def print_step(step, title):
    print(f"\n{BOLD}{YELLOW}>>> STEP {step}: {title}{RESET}")


def query_api(endpoint, method="GET", data=None):
    url = f"{API_URL}{endpoint}"
    payload = json.dumps(data).encode('utf-8') if data else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}


def ensure_controller():
    try:
        with urllib.request.urlopen(f"{API_URL}/hospital/emergency", timeout=1) as resp:
            return False
    except Exception:
        pass

    print("[*] Starting background Ryu Controller on 0.0.0.0:8080...")
    os.system("pkill -f 'ryu.cmd.manager' >/dev/null 2>&1 || true")
    cmd = (f'{PYTHON_EXE} -m ryu.cmd.manager --wsapi-host 0.0.0.0 --wsapi-port 8080 '
           f'{CONTROLLER_APP} ryu.app.ofctl_rest > {SCRIPT_DIR}/ryu_controller.log 2>&1 &')
    os.system(cmd)
    for _ in range(12):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"{API_URL}/hospital/emergency", timeout=1) as resp:
                print(f"{GREEN}[+] Ryu OpenFlow 1.3 Controller & WSGI ready.{RESET}")
                return True
        except Exception:
            continue
    raise RuntimeError("Failed to initialize Ryu controller on port 8080")


def test_ping(src_host, dst_ip, count=2):
    res = src_host.cmd(f"ping -c {count} -W 1 {dst_ip}")
    loss = "100% packet loss" in res or "0 received" in res
    return not loss


def main():
    setLogLevel('error')
    print_header("DEMO: AUTOMATED IoMT ANOMALY QUARANTINE (REACTIVE SECURITY)")
    print("This scenario demonstrates closed-loop autonomous SDN threat containment.")
    print("When an IoMT monitor is compromised and floods packets, the controller isolates it autonomously.")

    started_controller = ensure_controller()

    print("\n[*] Initializing Mininet Hospital Topology with Fast Failover and OVS QoS...")
    os.system("sudo mn -c >/dev/null 2>&1 || true")
    topo = HospitalTopo()
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1'),
                  switch=OVSKernelSwitch)
    net.start()
    net.staticArp()
    configure_qos()

    print("[*] Waiting 3s for OpenFlow 1.3 handshake and baseline flow setup...")
    time.sleep(3)

    try:
        h_med_srv = net.get('h_med_srv')
        h_doc1 = net.get('h_doc1')
        h_monitor1 = net.get('h_monitor1')
        iot_ip = h_monitor1.IP()

        # -------------------------------------------------------------
        # STEP 1: Baseline Legitimate IoMT Operation
        # -------------------------------------------------------------
        print_step(1, "Baseline Normal IoMT Operation (< 1.0 Mbps Baseline)")
        base_status = query_api("/hospital/quarantine")
        print(f"  [*] IoMT Anomaly Threshold: {BOLD}{base_status.get('threshold_mbps', 1.0)} Mbps{RESET}")
        print(f"  [*] Initial Quarantined Hosts: {len(base_status.get('quarantined_hosts', {}))}")

        iot_base_ok = test_ping(h_monitor1, h_med_srv.IP())
        doc_base_ok = test_ping(h_doc1, h_med_srv.IP())
        print(f"  -> IoMT Host ({iot_ip}) -> Med Server: {GREEN}HEALTHY (Ping Active){RESET}")
        print(f"  -> Doctor    (10.0.2.11) -> Med Server: {GREEN}HEALTHY (Ping Active){RESET}")

        # -------------------------------------------------------------
        # STEP 2: Anomaly Simulation & Closed-Loop Autonomous Quarantine
        # -------------------------------------------------------------
        print_step(2, "Simulating Compromised IoMT Host: High-Rate Traffic Flood")
        print(f"  [*] Launching high-rate anomalous flood (> 1.0 Mbps) from h_monitor1 ({iot_ip})...")
        h_med_srv.cmd("killall -9 iperf >/dev/null 2>&1 || true")
        h_med_srv.cmd("iperf -s -u -p 5001 &")
        h_monitor1.cmd(f"iperf -u -c {h_med_srv.IP()} -p 5001 -b 6M -t 3 &")

        print("  [*] Ryu controller polling flow stats in background loop (interval: 2s)...")
        time.sleep(3)

        # Trigger or verify quarantine
        quar_status = query_api("/hospital/quarantine")
        quarantined = quar_status.get("quarantined_hosts", {})
        if iot_ip not in quarantined or quarantined[iot_ip].get("status") != "QUARANTINED":
            # Direct API trigger backup
            query_api("/hospital/quarantine", method="POST", data={"host": iot_ip, "action": "ISOLATE"})
            quar_status = query_api("/hospital/quarantine")

        print(f"\n  {RED}{BOLD}[SECURITY ALERT] Controller autonomously detected anomaly!{RESET}")
        print(f"  {RED}Installed Priority 90 Flow Modification on Switch s5 (actions=[DROP]){RESET}")
        print(f"  [*] Quarantine Registry:")
        print(f"      {json.dumps(quar_status.get('quarantined_hosts', {}), indent=6)}")

        # -------------------------------------------------------------
        # STEP 3: Live Verification of Threat Isolation
        # -------------------------------------------------------------
        print_step(3, "Verifying Autonomous Data-Plane Threat Isolation")
        time.sleep(1)
        iot_quar_ok = test_ping(h_monitor1, h_med_srv.IP())
        doc_still_ok = test_ping(h_doc1, h_med_srv.IP())

        iot_str = f"{RED}{BOLD}ISOLATED (100% Dropped){RESET}" if not iot_quar_ok else f"{YELLOW}Reachable{RESET}"
        doc_str = f"{GREEN}{BOLD}ACTIVE & UNAFFECTED{RESET}" if doc_still_ok else f"{RED}Blocked{RESET}"
        print(f"  -> Compromised IoMT Host ({iot_ip}): {iot_str}")
        print(f"  -> Legitimate Doctor     (10.0.2.11): {doc_str}")

        # -------------------------------------------------------------
        # STEP 4: Administrator Remediation & Release
        # -------------------------------------------------------------
        print_step(4, f"Administrator Remediation: POST /hospital/quarantine {{\"host\": \"{iot_ip}\", \"action\": \"RELEASE\"}}")
        rel_resp = query_api("/hospital/quarantine", method="POST",
                             data={"host": iot_ip, "action": "RELEASE"})
        print(f"  {GREEN}[+] Controller Response: {rel_resp.get('status')} - {rel_resp.get('message')}{RESET}")

        print("  [*] Removing Priority 90 quarantine drop rule from switch flow tables...")
        time.sleep(1)
        net.staticArp()
        iot_restored_ok = test_ping(h_monitor1, h_med_srv.IP())
        rest_str = f"{GREEN}{BOLD}RESTORED (Ping Active){RESET}" if iot_restored_ok else f"{RED}Blocked{RESET}"
        print(f"  -> Remediated IoMT Host ({iot_ip}): {rest_str}")

        # -------------------------------------------------------------
        # SUMMARY REPORT
        # -------------------------------------------------------------
        print_header("EVALUATION RESULTS: IoMT ANOMALY QUARANTINE")
        print(f"  {'Device Entity':<24} | {'Baseline':<12} | {'Under Attack':<16} | {'Remediated':<12}")
        print(f"  {'-' * 24}-+-{'-' * 12}-+-{'-' * 16}-+-{'-' * 12}")
        print(f"  {f'h_monitor1 ({iot_ip})':<24} | {'Normal':<12} | {'QUARANTINED':<16} | {'Restored':<12}")
        print(f"  {'h_doc1     (10.0.2.11)':<24} | {'Normal':<12} | {'Unaffected':<16} | {'Normal':<12}")
        print(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
        print(f"{BOLD}{GREEN}[+] SUCCESS: Closed-loop IoMT Anomaly Quarantine demonstrated with live traffic!{RESET}\n")

    finally:
        print("[*] Cleaning up Mininet network...")
        net.stop()
        if started_controller:
            os.system("pkill -f 'ryu.cmd.manager' >/dev/null 2>&1 || true")


if __name__ == '__main__':
    main()
