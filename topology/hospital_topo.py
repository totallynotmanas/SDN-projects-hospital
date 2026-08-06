#!/usr/bin/python3
"""
Custom Mininet Topology for a Hospital Network

Departments:
- Datacenter (Medical DB, Admin DB)
- Medical (Doctors, Nurses)
- Admin (Management, HR)
- IoT/Medical Devices (MRI, Monitors)
- Guest WiFi
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

        # Link switches together (Star topology from core)
        self.addLink(s_core, s_dc)
        self.addLink(s_core, s_med)
        self.addLink(s_core, s_admin)
        self.addLink(s_core, s_iot)
        self.addLink(s_core, s_guest)

        # Datacenter Hosts
        # 10.0.1.X - Datacenter
        h_med_srv = self.addHost('h_med_srv', ip='10.0.1.10/16', mac='00:00:00:00:01:10')
        h_adm_srv = self.addHost('h_adm_srv', ip='10.0.1.20/16', mac='00:00:00:00:01:20')
        self.addLink(h_med_srv, s_dc)
        self.addLink(h_adm_srv, s_dc)

        # Medical Department Hosts
        # 10.0.2.X - Medical
        h_doc1 = self.addHost('h_doc1', ip='10.0.2.11/16', mac='00:00:00:00:02:11')
        h_nurse1 = self.addHost('h_nurse1', ip='10.0.2.12/16', mac='00:00:00:00:02:12')
        self.addLink(h_doc1, s_med)
        self.addLink(h_nurse1, s_med)

        # Admin Department Hosts
        # 10.0.3.X - Admin
        h_admin1 = self.addHost('h_admin1', ip='10.0.3.11/16', mac='00:00:00:00:03:11')
        h_hr1 = self.addHost('h_hr1', ip='10.0.3.12/16', mac='00:00:00:00:03:12')
        self.addLink(h_admin1, s_admin)
        self.addLink(h_hr1, s_admin)

        # IoT/Medical Devices Hosts
        # 10.0.4.X - IoT
        h_mri1 = self.addHost('h_mri1', ip='10.0.4.11/16', mac='00:00:00:00:04:11')
        h_monitor1 = self.addHost('h_monitor1', ip='10.0.4.12/16', mac='00:00:00:00:04:12')
        self.addLink(h_mri1, s_iot)
        self.addLink(h_monitor1, s_iot)

        # Guest WiFi Hosts
        # 10.0.5.X - Guest
        h_guest1 = self.addHost('h_guest1', ip='10.0.5.11/16', mac='00:00:00:00:05:11')
        h_guest2 = self.addHost('h_guest2', ip='10.0.5.12/16', mac='00:00:00:00:05:12')
        self.addLink(h_guest1, s_guest)
        self.addLink(h_guest2, s_guest)


def configure_qos():
    info('*** Configuring OVS QoS Queues on s2-eth1 (Datacenter to Core)\n')
    # Clear existing QoS
    os.system("ovs-vsctl clear Port s2-eth1 qos")
    # Create linux-htb QoS with 3 queues
    # q0: Default (10Mbps min, 100Mbps max)
    # q1: High Priority / Medical (50Mbps min, 100Mbps max)
    # q2: Low Priority / IoT (Max 1Mbps)
    cmd = (
        "ovs-vsctl -- set Port s2-eth1 qos=@newqos -- "
        "--id=@newqos create QoS type=linux-htb other-config:max-rate=100000000 queues=0=@q0,1=@q1,2=@q2 -- "
        "--id=@q0 create Queue other-config:min-rate=10000000 other-config:max-rate=100000000 -- "
        "--id=@q1 create Queue other-config:min-rate=50000000 other-config:max-rate=100000000 -- "
        "--id=@q2 create Queue other-config:max-rate=1000000"
    )
    os.system(cmd)


def run_custom_topo():
    topo = HospitalTopo()
    
    # Connect to Remote Ryu Controller running on localhost, default port 6653
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1'), switch=OVSKernelSwitch)
    
    info('*** Starting network\n')
    net.start()
    
    # Apply QoS settings after switches are started
    configure_qos()
    
    info('*** Running CLI\n')
    CLI(net)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_custom_topo()
