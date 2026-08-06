#!/usr/bin/python3
import time
import os
import csv
import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

PCAP_DIR = os.path.join(REPO_ROOT, 'pcap')
CSV_FILE = os.path.join(REPO_ROOT, 'qos_results.csv')
CONTROLLER_LOG = os.path.join(REPO_ROOT, 'ryu_controller.log')
CONTROLLER_APP = os.path.join(REPO_ROOT, 'controller', 'hospital_controller.py')
RYU_CMD = 'python -m ryu.cmd.manager'
MED_SRV_IP = '10.0.1.10'

# Add parent directory to path to import topology
sys.path.append(REPO_ROOT)
from topology.hospital_topo import HospitalTopo, configure_qos


def start_controller():
    info('*** Starting Ryu Controller (with REST API) in background...\n')
    cmd = (f'{RYU_CMD} {CONTROLLER_APP} ryu.app.ofctl_rest '
           f'> {CONTROLLER_LOG} 2>&1 &')
    os.system(cmd)
    time.sleep(5)  # Wait for Ryu to initialize


def stop_controller():
    os.system(f'pkill -f {RYU_CMD}')


def run_iperf(client, duration=5, reverse=False):
    flag = ' -R' if reverse else ''
    res = client.cmd(f'iperf -c {MED_SRV_IP} -t {duration} -y C{flag}')
    # -y C outputs CSV; the bandwidth (bps) is the last field.
    if res and len(res.strip().split(',')) > 8:
        try:
            bw_bps = int(res.strip().split(',')[-1])
            return bw_bps / 1_000_000
        except ValueError:
            return 0.0
    return 0.0


def start_tcpdump(host, pcap_path):
    host.cmd(f'nohup tcpdump -i {host.name}-eth0 -w {pcap_path} '
             '>/dev/null 2>&1 &')


def stop_tcpdump(host):
    host.cmd('pkill -x tcpdump')


def run_experiments():
    setLogLevel('info')

    start_controller()

    topo = HospitalTopo()
    net = Mininet(topo=topo,
                  controller=lambda name: RemoteController(name, ip='127.0.0.1'),
                  switch=OVSKernelSwitch)

    info('*** Starting network...\n')
    net.start()

    info('*** Waiting for switches to connect to controller...\n')
    time.sleep(5)

    h_med_srv = net.get('h_med_srv')
    h_doc1 = net.get('h_doc1')
    h_mri1 = net.get('h_mri1')

    info('*** Starting iperf server on Med Server...\n')
    h_med_srv.cmd('iperf -s >/dev/null 2>&1 &')
    time.sleep(1)

    os.makedirs(PCAP_DIR, exist_ok=True)
    results = []

    # ============================================================
    # PHASE 1: BASELINE (BEFORE QoS queues are applied)
    # NOTE: we use iperf in reverse mode (-R) because the controller's
    # QoS rules match ipv4_dst and shape egress on s2 -> core (port 1).
    # Reverse mode makes the SERVER (h_med_srv) the sender, so traffic
    # actually hits the configured queues.
    # ============================================================
    info('*** PHASE 1: BASELINE (no QoS) - capturing packets...\n')
    base_pcap = os.path.join(PCAP_DIR, 'baseline_capture.pcap')
    start_tcpdump(h_med_srv, base_pcap)

    info('*** Running Baseline Test: Medical (no QoS)...\n')
    base_med = run_iperf(h_doc1, reverse=True)

    info('*** Running Baseline Test: IoT (no QoS)...\n')
    base_iot = run_iperf(h_mri1, reverse=True)

    stop_tcpdump(h_med_srv)
    results.append(('Medical (Queue 1)', 'Before', base_med))
    results.append(('IoT (Queue 2)', 'Before', base_iot))

    # ============================================================
    # Apply QoS queues (linux-htb on s2-eth1)
    # ============================================================
    info('*** Applying OVS QoS queues...\n')
    configure_qos()
    time.sleep(3)  # Let queue configuration settle

    # ============================================================
    # PHASE 2: WITH QoS enforcement + packet capture
    # ============================================================
    info('*** PHASE 2: WITH QoS - capturing packets...\n')
    qos_pcap = os.path.join(PCAP_DIR, 'qos_capture.pcap')
    start_tcpdump(h_med_srv, qos_pcap)

    info('*** Running Bandwidth Test: Medical (High Priority - Queue 1)...\n')
    qos_med = run_iperf(h_doc1, reverse=True)

    info('*** Running Bandwidth Test: IoT (Throttled - Queue 2)...\n')
    qos_iot = run_iperf(h_mri1, reverse=True)

    stop_tcpdump(h_med_srv)
    results.append(('Medical (Queue 1)', 'After', qos_med))
    results.append(('IoT (Queue 2)', 'After', qos_iot))

    info('*** Stopping iperf server...\n')
    h_med_srv.cmd('pkill -x iperf')

    info('*** Stopping network and controller...\n')
    net.stop()
    stop_controller()

    info(f'*** Saving bandwidth results to {CSV_FILE}...\n')
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Traffic_Type', 'Phase', 'Bandwidth_Mbps'])
        writer.writerows(results)

    info('*** Experiment Complete. Run plot_results.py to generate charts.\n')


if __name__ == '__main__':
    # Cleanup before starting
    os.system('sudo mn -c > /dev/null 2>&1')
    os.system(f'pkill -f {RYU_CMD}')
    run_experiments()
