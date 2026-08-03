#!/usr/bin/python3
import time
import os
import csv
import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info

# Add parent directory to path to import topology
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from topology.hospital_topo import HospitalTopo, configure_qos

def run_experiments():
    setLogLevel('info')
    
    info('*** Starting Ryu Controller in background...\n')
    ryu_cmd = "ryu-manager ../controller/hospital_controller.py > /dev/null 2>&1 &"
    os.system(ryu_cmd)
    time.sleep(3) # Wait for Ryu to initialize

    topo = HospitalTopo()
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1'), switch=OVSKernelSwitch)
    
    info('*** Starting network...\n')
    net.start()
    
    # Configure our QoS queues via ovs-vsctl
    configure_qos()
    
    info('*** Waiting for switches to connect to controller...\n')
    time.sleep(5)

    h_med_srv = net.get('h_med_srv')
    h_doc1 = net.get('h_doc1')
    h_mri1 = net.get('h_mri1')

    # 1. Traffic Monitoring (Rubric Point 4)
    info('*** Starting tcpdump on Med Server for traffic capture...\n')
    os.system("mkdir -p ../pcap")
    h_med_srv.cmd("tcpdump -i h_med_srv-eth0 -w ../pcap/qos_capture.pcap &")
    
    # 2. Performance Analysis (Rubric Point 5)
    info('*** Starting iperf server on Med Server...\n')
    h_med_srv.cmd("iperf -s &")
    time.sleep(1)

    results = []

    # Test 1: Medical Traffic (High Priority - Queue 1)
    info('*** Running Bandwidth Test: Medical (High Priority)...\n')
    # -y C outputs CSV format. We extract the bandwidth in bps.
    res1 = h_doc1.cmd("iperf -c 10.0.1.10 -t 5 -y C")
    if res1 and len(res1.strip().split(',')) > 8:
        bw_bps = int(res1.strip().split(',')[-1])
        results.append(("Medical (Queue 1)", bw_bps / 1_000_000))
    else:
        results.append(("Medical (Queue 1)", 0))
    
    # Test 2: IoT Traffic (Low Priority - Queue 2)
    info('*** Running Bandwidth Test: IoT (Throttled)...\n')
    res2 = h_mri1.cmd("iperf -c 10.0.1.10 -t 5 -y C")
    if res2 and len(res2.strip().split(',')) > 8:
        bw_bps = int(res2.strip().split(',')[-1])
        results.append(("IoT (Queue 2)", bw_bps / 1_000_000))
    else:
        results.append(("IoT (Queue 2)", 0))

    info('*** Stopping iperf and tcpdump...\n')
    h_med_srv.cmd("kill %iperf")
    h_med_srv.cmd("kill %tcpdump")

    info('*** Stopping network and controller...\n')
    net.stop()
    os.system("pkill -f ryu-manager")
    
    # Write results to CSV for charting
    csv_file = '../qos_results.csv'
    info(f'*** Saving bandwidth results to {csv_file}...\n')
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Traffic_Type', 'Bandwidth_Mbps'])
        writer.writerows(results)

    info('*** Experiment Complete. Run plot_results.py to generate charts.\n')

if __name__ == '__main__':
    # Cleanup before starting
    os.system("sudo mn -c > /dev/null 2>&1")
    os.system("pkill -f ryu-manager")
    run_experiments()
