#!/usr/bin/python3
"""
Custom Mininet Topology for a Hospital Network

Departments:
- Datacenter (Medical DB, Admin DB)
- Medical (Doctors, Nurses)
- Admin (Management, HR)
- IoT/Medical Devices (MRI, Monitors)
- Guest WiFi
- Quarantine / Honeypot Zone (for isolated compromised IoMT devices)

Features:
- Dual redundant aggregation links (s1 <-> s2) for OpenFlow Fast Failover (FF).
- Deterministic port allocation for Fast Failover group matching.
- Linux-HTB QoS queues with Code Blue emergency preemption queue (Queue 3).
"""

import os
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


class HospitalTopo(Topo):
    def build(self):
        # Create core switch and datacenter switch
        s_core = self.addSwitch('s1', dpid='0000000000000001')
        s_dc = self.addSwitch('s2', dpid='0000000000000002')
        
        # Create departmental access switches
        s_med = self.addSwitch('s3', dpid='0000000000000003')
        s_admin = self.addSwitch('s4', dpid='0000000000000004')
        s_iot = self.addSwitch('s5', dpid='0000000000000005')
        s_guest = self.addSwitch('s6', dpid='0000000000000006')

        # Link switches together with explicit port assignments
        # s1 <-> s2: Dual redundant links for Fast Failover (Idea 3)
        # Primary Link: s1-eth1 <-> s2-eth1
        self.addLink(s_core, s_dc, port1=1, port2=1)
        # Backup Redundant Link: s1-eth6 <-> s2-eth2
        self.addLink(s_core, s_dc, port1=6, port2=2)

        # Departmental links to Core
        self.addLink(s_core, s_med, port1=2, port2=1)
        self.addLink(s_core, s_admin, port1=3, port2=1)
        self.addLink(s_core, s_iot, port1=4, port2=1)
        self.addLink(s_core, s_guest, port1=5, port2=1)

        # Datacenter Hosts on s2
        # 10.0.1.X - Datacenter
        h_med_srv = self.addHost('h_med_srv', ip='10.0.1.10/16', mac='00:00:00:00:01:10')
        h_adm_srv = self.addHost('h_adm_srv', ip='10.0.1.20/16', mac='00:00:00:00:01:20')
        self.addLink(h_med_srv, s_dc, port2=3)
        self.addLink(h_adm_srv, s_dc, port2=4)

        # Quarantine / Honeypot Host on s1 port 7 (Idea 2)
        # Note: Name is h_quar to strictly respect Linux IFNAMSIZ 15-char limit (h_quar-eth0)
        h_quar = self.addHost('h_quar', ip='10.0.99.10/16', mac='00:00:00:00:99:10')
        self.addLink(h_quar, s_core, port2=7)

        # Medical Department Hosts on s3
        # 10.0.2.X - Medical
        h_doc1 = self.addHost('h_doc1', ip='10.0.2.11/16', mac='00:00:00:00:02:11')
        h_nurse1 = self.addHost('h_nurse1', ip='10.0.2.12/16', mac='00:00:00:00:02:12')
        self.addLink(h_doc1, s_med)
        self.addLink(h_nurse1, s_med)

        # Admin Department Hosts on s4
        # 10.0.3.X - Admin
        h_admin1 = self.addHost('h_admin1', ip='10.0.3.11/16', mac='00:00:00:00:03:11')
        h_hr1 = self.addHost('h_hr1', ip='10.0.3.12/16', mac='00:00:00:00:03:12')
        self.addLink(h_admin1, s_admin)
        self.addLink(h_hr1, s_admin)

        # IoT/Medical Devices Hosts on s5
        # 10.0.4.X - IoT
        h_mri1 = self.addHost('h_mri1', ip='10.0.4.11/16', mac='00:00:00:00:04:11')
        h_monitor1 = self.addHost('h_monitor1', ip='10.0.4.12/16', mac='00:00:00:00:04:12')
        self.addLink(h_mri1, s_iot)
        self.addLink(h_monitor1, s_iot)

        # Guest WiFi Hosts on s6
        # 10.0.5.X - Guest
        h_guest1 = self.addHost('h_guest1', ip='10.0.5.11/16', mac='00:00:00:00:05:11')
        h_guest2 = self.addHost('h_guest2', ip='10.0.5.12/16', mac='00:00:00:00:05:12')
        self.addLink(h_guest1, s_guest)
        self.addLink(h_guest2, s_guest)


def configure_qos():
    info('*** Configuring OVS QoS Queues on Core (s1) and Datacenter (s2)...\n')
    # Configure bidirectional QoS on primary and backup aggregation links
    for port in ['s1-eth1', 's1-eth6', 's2-eth1', 's2-eth2']:
        os.system(f"ovs-vsctl clear Port {port} qos >/dev/null 2>&1")
        # Queues:
        # q0: Default (10Mbps min, 100Mbps max)
        # q1: High Priority / Medical baseline (50Mbps min, 100Mbps max)
        # q2: Low Priority / IoT & Throttled Admin during Code Blue (1Mbps max)
        # q3: Code Blue Emergency Preemption Queue (85Mbps min, 100Mbps max)
        cmd = (
            f"ovs-vsctl -- set Port {port} qos=@newqos -- "
            f"--id=@newqos create QoS type=linux-htb other-config:max-rate=100000000 "
            f"queues=0=@q0,1=@q1,2=@q2,3=@q3 -- "
            f"--id=@q0 create Queue other-config:min-rate=10000000 other-config:max-rate=100000000 -- "
            f"--id=@q1 create Queue other-config:min-rate=50000000 other-config:max-rate=100000000 -- "
            f"--id=@q2 create Queue other-config:max-rate=1000000 -- "
            f"--id=@q3 create Queue other-config:min-rate=85000000 other-config:max-rate=100000000 >/dev/null 2>&1"
        )
        os.system(cmd)
    info('*** OVS QoS Queues configured on s1-eth1, s1-eth6, s2-eth1, and s2-eth2\n')


def run_custom_topo():
    topo = HospitalTopo()
    
    # Connect to Remote Ryu Controller running on localhost, default port 6653
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1'), switch=OVSKernelSwitch)
    
    info('*** Starting network\n')
    net.start()
    
    # Pre-populate static ARP cache to prevent broadcast ARP storms on redundant links
    net.staticArp()
    
    # Apply QoS settings after switches are started
    configure_qos()
    
    info('*** Running CLI\n')
    CLI(net)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_custom_topo()

