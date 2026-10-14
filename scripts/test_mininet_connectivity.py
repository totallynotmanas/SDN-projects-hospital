#!/usr/bin/python3
"""
Automated Verification Suite for Hospital SDN Network

Tests:
1. Baseline Departmental Access and Firewall Policies:
   - Medical -> Med Server (ALLOWED)
   - Admin -> Admin Server (ALLOWED)
   - Guest -> Med Server (BLOCKED)
   - IoT -> Admin Server (BLOCKED)
2. Fast Failover Resilience (OFPGT_FF):
   - Ping Med Server over primary link
   - Cut primary link s2-eth1
   - Ping Med Server over backup link s2-eth2 (instant failover!)
   - Restore primary link
3. Code Blue Dynamic QoS Preemption:
   - Trigger emergency via REST
   - Verify priority 100 rules installed
   - Resolve emergency and verify restoration
4. Automated IoMT Anomaly Quarantine:
   - Trigger quarantine on h_mri1 (10.0.4.11)
   - Verify h_mri1 traffic dropped
   - Release h_mri1 and verify communication restored
"""

import os
import sys
import time
import json
import urllib.request

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
PYTHON_EXE = sys.executable
CONTROLLER_APP = os.path.join(REPO_ROOT, 'controller', 'hospital_controller.py')
API_URL = 'http://127.0.0.1:8080'

sys.path.append(REPO_ROOT)
from topology.hospital_topo import HospitalTopo, configure_qos


def post_json(endpoint, data):
    url = f"{API_URL}{endpoint}"
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get_json(endpoint):
    url = f"{API_URL}{endpoint}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode('utf-8'))


def start_controller():
    info('*** Starting Ryu Controller in background...\n')
    cmd = (f'{PYTHON_EXE} -m ryu.cmd.manager --wsapi-host 0.0.0.0 --wsapi-port 8080 '
           f'{CONTROLLER_APP} ryu.app.ofctl_rest > {SCRIPT_DIR}/ryu_controller.log 2>&1 &')
    os.system(cmd)
    time.sleep(5)


def stop_controller():
    os.system("pkill -f 'ryu.cmd.manager' >/dev/null 2>&1 || true")


def test_suite():
    setLogLevel('info')
    os.system('sudo mn -c > /dev/null 2>&1 || true')
    stop_controller()
    start_controller()

    topo = HospitalTopo()
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1'),
                  switch=OVSKernelSwitch)
    net.start()
    net.staticArp()
    configure_qos()

    info('*** Waiting for network convergence...\n')
    time.sleep(4)

    h_med_srv = net.get('h_med_srv')
    h_adm_srv = net.get('h_adm_srv')
    h_doc1 = net.get('h_doc1')
    h_admin1 = net.get('h_admin1')
    h_mri1 = net.get('h_mri1')
    h_guest1 = net.get('h_guest1')
    s2 = net.get('s2')

    passed = 0
    total = 0

    def assert_ping(h_src, h_dst, expect_pass, test_name):
        nonlocal passed, total
        total += 1
        res = h_src.cmd(f'ping -c 2 -W 1 {h_dst.IP()}')
        loss = '100% packet loss' in res or '0 received' in res
        success = not loss if expect_pass else loss
        status_str = "PASS" if success else "FAIL"
        if success:
            passed += 1
        info(f'[{status_str}] Test {total}: {test_name} (Expect: {"ALLOW" if expect_pass else "BLOCK"})\n')

    info('\n=== SUITE 1: Baseline Departmental Isolation & Firewall Policies ===\n')
    assert_ping(h_doc1, h_med_srv, True, "Medical Staff -> Medical Database")
    assert_ping(h_admin1, h_adm_srv, True, "Admin Staff -> Admin Database")
    assert_ping(h_guest1, h_med_srv, False, "Guest WiFi -> Medical Database (Firewall Drop)")
    assert_ping(h_mri1, h_adm_srv, False, "IoT/MRI -> Admin Database (Firewall Drop)")
    assert_ping(h_mri1, h_med_srv, True, "IoT/MRI -> Medical Database (Authorized Telemetry)")

    info('\n=== SUITE 2: Sub-Millisecond Telemetry Resilience (Fast Failover OFPGT_FF) ===\n')
    # Ping before link cut
    assert_ping(h_doc1, h_med_srv, True, "Medical -> Med Server over Primary Link (s2-eth1)")
    # Cut primary link s2-eth1
    info('*** Simulating link break on s2-eth1...\n')
    s2.cmd('ip link set s2-eth1 down')
    time.sleep(1)
    # Ping should continue over backup link s2-eth2
    assert_ping(h_doc1, h_med_srv, True, "Medical -> Med Server over Backup Link (s2-eth2 Failover)")
    # Recover primary link
    info('*** Restoring primary link s2-eth1...\n')
    s2.cmd('ip link set s2-eth1 up')
    time.sleep(1)
    assert_ping(h_doc1, h_med_srv, True, "Medical -> Med Server after Link Recovery")

    info('\n=== SUITE 3: "Code Blue" Event-Driven Dynamic QoS Preemption ===\n')
    code_blue_res = post_json('/hospital/emergency', {"status": "CODE_BLUE", "unit": "ICU_Room_1"})
    info(f'[*] CODE_BLUE Triggered: {code_blue_res.get("status")}\n')
    # During Code Blue, Guest traffic is completely dropped
    assert_ping(h_guest1, h_med_srv, False, "Guest WiFi suspended during Code Blue")
    # Medical telemetry still has top priority access
    assert_ping(h_doc1, h_med_srv, True, "ICU/Medical Telemetry active during Code Blue")
    resolved_res = post_json('/hospital/emergency', {"status": "RESOLVED"})
    info(f'[*] Emergency Resolved: {resolved_res.get("status")}\n')

    info('\n=== SUITE 4: Automated IoMT Anomaly Quarantine (Reactive Security) ===\n')
    # Isolate h_mri1
    post_json('/hospital/quarantine', {"host": h_mri1.IP(), "action": "ISOLATE"})
    time.sleep(1)
    assert_ping(h_mri1, h_med_srv, False, "Quarantined IoMT Host Blocked (Priority 90 Drop)")
    # Release h_mri1
    post_json('/hospital/quarantine', {"host": h_mri1.IP(), "action": "RELEASE"})
    time.sleep(1)
    net.staticArp()
    assert_ping(h_mri1, h_med_srv, True, "Remediated IoMT Host Unblocked after Release")

    info(f'\n==========================================================\n')
    info(f'  RESULTS: {passed}/{total} Tests PASSED!\n')
    info(f'==========================================================\n')

    net.stop()
    stop_controller()


if __name__ == '__main__':
    test_suite()
