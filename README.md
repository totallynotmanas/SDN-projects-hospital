# Hospital SDN Project: Intelligent QoS Preemption, IoMT Quarantine & Telemetry Resilience

This project implements an enterprise-grade Software-Defined Network (SDN) for a modern smart hospital. It uses **Mininet** to emulate the physical data plane and **Ryu** as the OpenFlow 1.3 controller to enforce micro-segmentation, dynamic event-driven QoS, autonomous intrusion quarantine, and sub-millisecond telemetry resilience.

---

## 🌟 Advanced SDN Features (Exam & Production Highlights)

### 1. Idea 1: "Code Blue" Event-Driven Dynamic QoS Preemption Engine
* **The Problem**: In a hospital, an ICU patient crashing or an emergency surgery cannot compete for network capacity with routine MRI transfers, administrative backups, or visitor Wi-Fi streams.
* **The SDN Novelty**: An **Event-Driven Preemption Engine** exposed via a Ryu WSGI REST endpoint (`/hospital/emergency`).
* **Implementation**:
  * Medical staff or telemetry monitors trigger an emergency: `POST /hospital/emergency {"status": "CODE_BLUE", "unit": "ICU_Room_1"}`.
  * The controller dynamically installs **high-priority OpenFlow rules (`priority=100`)**:
    * **ICU / Medical Telemetry**: Assigned to Queue 3 (Ultra-Low-Latency, 85 Mbps guaranteed bandwidth).
    * **Admin Department**: Throttled down to Queue 2 (1 Mbps minimum bandwidth).
    * **Guest Wi-Fi**: Temporarily suspended / dropped (`actions=[]`).
  * When `{"status": "RESOLVED"}` is posted, the controller cleanly removes the preemption flows, seamlessly restoring baseline departmental QoS and firewall states.

### 2. Idea 2: Automated IoMT Anomaly Quarantine (Reactive Security)
* **The Problem**: Infusion pumps, patient vitals monitors, and IoMT devices are high-risk targets for ransomware and lateral malware propagation.
* **The SDN Novelty**: **Closed-loop telemetry stats monitoring and autonomous data-plane isolation**.
* **Implementation**:
  * In Ryu, a background thread periodically polls OpenFlow stats (`OFPFlowStatsRequest`) every 2 seconds.
  * The controller computes live byte transmission rates. If an IoMT host (subnet `10.0.4.0/24`) exceeds its 1.0 Mbps baseline rate (simulating compromised host port-scanning or data exfiltration):
    * The controller logs: `[SECURITY ALERT] IoMT Host 10.0.4.x anomalous traffic detected -> Quarantined!`
    * Automatically injects **quarantine flow rules (`priority=90`, `actions=[]`)** on edge switches to immediately isolate the compromised host from the rest of the hospital.
  * Administrators can inspect quarantined devices via `GET /hospital/quarantine` and restore remediated devices via `POST /hospital/quarantine {"host": "10.0.4.11", "action": "RELEASE"}`.

### 3. Idea 3: Sub-Millisecond Telemetry Resilience via Fast Failover Groups (`OFPGT_FF`)
* **The Problem**: If an aggregation link breaks in a hospital, reactive path recomputation across the controller introduces packet loss and latency spikes that can disconnect life-critical patient monitors.
* **The SDN Novelty**: **Hardware-level data-plane Fast Failover (`OFPGT_FF`) without controller round-trips**.
* **Implementation**:
  * Dual redundant links connect the Datacenter Switch (`s2`) and Core Switch (`s1`).
  * Configured OpenFlow 1.3 Fast Failover Group Tables (`group_id=1`):
    * **Bucket 1**: Monitors `watch_port=1` (Primary link to Core).
    * **Bucket 2**: Monitors `watch_port=2` (Redundant backup link to Core).
  * Outbound telemetry and datacenter flows output to `group:1`.
  * If the primary link goes down, Open vSwitch automatically redirects packets to the backup link at the kernel/data-plane layer in **$< 10\text{ ms}$**, before the controller even finishes processing link-down notifications!

---

## 🏗️ OpenFlow Flow Priority Hierarchy

The controller organizes flow tables into a strict, conflict-free priority hierarchy:

| Priority | Category | OpenFlow Match / Action | Purpose |
| :---: | :---: | :---: | :--- |
| **100** | **Code Blue Preemption** | `ipv4_dst=10.0.2.0/24 -> Queue 3, Group 1`<br>`ipv4_dst=10.0.3.0/24 -> Queue 2, Group 1`<br>`ipv4_dst=10.0.5.0/24 -> DROP` | Emergency telemetry prioritization & background throttling |
| **90** | **IoMT Quarantine** | `ipv4_src=10.0.4.X -> DROP` | Autonomous isolation of compromised medical devices |
| **20** | **Baseline QoS & Failover** | `ipv4_dst=10.0.2.0/24 -> Queue 1, Group 1`<br>`ipv4_dst=10.0.4.0/24 -> Queue 2, Group 1`<br>`ipv4_dst=10.0.1.0/24 -> Group 1` | Departmental QoS traffic steering & dual-bucket Fast Failover |
| **10** | **Baseline Firewall** | Guest isolation, IoT server isolation, Department boundary checks | Proactive hospital zone micro-segmentation |
| **1** | **L2 Learning** | `(in_port, eth_dst, eth_src) -> out_port` | Dynamic MAC learning with standby loop-prevention |
| **0** | **Table-Miss** | `Match: ANY -> Output: Controller` | Control-plane punt for unknown ARP / new packets |

---

## 💻 Running on macOS using Multipass

Because Mininet relies on Linux network namespaces, Open vSwitch kernel modules, and virtual ethernet (`veth`) pairs, Mininet cannot run directly on the macOS Darwin kernel. A lightweight Ubuntu Multipass VM provides the ideal Linux virtualization environment.

This repository includes **native macOS Multipass integration scripts** that handle VM provisioning, atomic code synchronization, and demo execution.

### Prerequisites on Mac

1. Install Multipass on macOS:
   ```bash
   brew install --cask multipass
   ```
   *(Or download the installer from [multipass.run](https://multipass.run/))*

### Step 1: One-Time VM Provisioning

Run the setup script from your macOS terminal:
```bash
./scripts/setup_multipass.sh
```
*This verifies or launches an Ubuntu LTS VM (named `refined-pup` or `hospital-sdn`), installs Mininet, Open vSwitch, tcpdump, iperf, Ryu, Flask, matplotlib, and pandas, and synchronizes your codebase into `~/hospital-sdn`.*

### Step 2: One-Click Execution from macOS

Use the `./scripts/run_multipass.sh` wrapper from your Mac terminal:

```bash
# Display VM IP address and available REST endpoints
./scripts/run_multipass.sh info

# Sync latest code from Mac to VM and launch Mininet CLI & Ryu
./scripts/run_multipass.sh network

# Run the Code Blue Dynamic QoS Preemption demo
./scripts/run_multipass.sh codeblue

# Run the IoMT Anomaly Quarantine demo
./scripts/run_multipass.sh quarantine

# Run the Fast Failover Sub-Millisecond Resilience demo
./scripts/run_multipass.sh failover

# Open the interactive curses Flow Console in VM
./scripts/run_multipass.sh console

# Run automated QoS benchmarks and fetch the chart (qos_comparison.png) to Mac
./scripts/run_multipass.sh experiments

# Drop into an interactive bash shell inside the VM
./scripts/run_multipass.sh shell
```

### Accessing the Controller REST API from your Mac Browser / Terminal

Because Ryu binds to `0.0.0.0:8080`, you can query the controller directly from your Mac terminal using the VM's IP address:

```bash
# Get your VM IP
VM_IP=$(multipass info refined-pup | awk '/IPv4:/ {print $2}')

# Query Emergency state
curl -s http://$VM_IP:8080/hospital/emergency | python3 -m json.tool

# Query IoMT Quarantine state
curl -s http://$VM_IP:8080/hospital/quarantine | python3 -m json.tool

# Query Fast Failover configuration
curl -s http://$VM_IP:8080/hospital/failover | python3 -m json.tool

# Dump live switch flows (Switch 1 / Core)
curl -s http://$VM_IP:8080/stats/flow/1 | python3 -m json.tool
```

---

## 🩺 Step-by-Step Feature Demos

### Demo 1: "Code Blue" Event-Driven Dynamic QoS Preemption

Run the interactive walkthrough:
```bash
./scripts/run_multipass.sh codeblue
```
Or trigger it manually via the CLI utility or `curl`:
```bash
# 1. Trigger Code Blue
python3 scripts/trigger_code_blue.py CODE_BLUE ICU_Room_1
# (or curl -X POST -H "Content-Type: application/json" -d '{"status":"CODE_BLUE","unit":"ICU_Room_1"}' http://127.0.0.1:8080/hospital/emergency)

# 2. Verify priority 100 rules on Datacenter switch s2:
sudo ovs-ofctl -O OpenFlow13 dump-flows s2 | grep "priority=100"

# 3. Resolve the emergency:
python3 scripts/trigger_code_blue.py RESOLVED
```

---

### Demo 2: Automated IoMT Anomaly Quarantine

Run the automated walkthrough:
```bash
./scripts/run_multipass.sh quarantine
```
Or test via the REST API:
```bash
# Manually isolate suspicious host
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"host": "10.0.4.11", "action": "ISOLATE"}' \
  http://127.0.0.1:8080/hospital/quarantine | python3 -m json.tool

# Verify quarantine registry
curl -s http://127.0.0.1:8080/hospital/quarantine | python3 -m json.tool

# Release host after disinfection
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"host": "10.0.4.11", "action": "RELEASE"}' \
  http://127.0.0.1:8080/hospital/quarantine | python3 -m json.tool
```

---

### Demo 3: Sub-Millisecond Telemetry Resilience (Fast Failover)

Run the fast failover demonstration:
```bash
./scripts/run_multipass.sh failover
```
*Shows Group Table 1 (`OFPGT_FF`) with Bucket 1 (`watch_port=1`) and Bucket 2 (`watch_port=2`). Cuts primary interface `s2-eth1` and demonstrates uninterrupted ping delivery over backup interface `s2-eth2`.*

---

## 🧪 Comprehensive Automated Test Suite (12/12 Passing)

Run the complete integration suite:
```bash
multipass exec refined-pup -- sudo PYTHONPATH=/usr/lib/python3/dist-packages:/home/ubuntu/hospital-sdn /home/ubuntu/venv/bin/python3 /home/ubuntu/hospital-sdn/scripts/test_mininet_connectivity.py
```

### Test Results Breakdown:
* **Suite 1: Baseline Micro-segmentation & Firewall**
  * `[PASS]` Medical Staff -> Medical Database (Authorized)
  * `[PASS]` Admin Staff -> Admin Database (Authorized)
  * `[PASS]` Guest Wi-Fi -> Medical Database (Dropped by Firewall)
  * `[PASS]` IoT Device -> Admin Database (Dropped by Firewall)
  * `[PASS]` IoT Device -> Medical Database (Authorized Telemetry)
* **Suite 2: Fast Failover Resilience (`OFPGT_FF`)**
  * `[PASS]` Medical Staff -> Medical Server over Primary Link (`s2-eth1`)
  * `[PASS]` Medical Staff -> Medical Server over Backup Link (`s2-eth2` link-down failover)
  * `[PASS]` Medical Staff -> Medical Server after Primary Link Recovery
* **Suite 3: "Code Blue" Event-Driven Dynamic QoS Preemption**
  * `[PASS]` Guest Wi-Fi suspended during Code Blue (`priority=100` DROP)
  * `[PASS]` ICU / Medical Telemetry active and prioritized during Code Blue
* **Suite 4: Automated IoMT Anomaly Quarantine**
  * `[PASS]` Quarantined IoMT Host Blocked (`priority=90` DROP)
  * `[PASS]` Remediated IoMT Host Unblocked after Administrator Release

---

## 📊 Automated QoS Evaluation & Charts

To measure bandwidth before and after QoS, and during Code Blue preemption:
```bash
./scripts/run_multipass.sh experiments
```
This runs three benchmark phases:
1. **Phase 1: Baseline (Unshaped)**: Measures baseline throughput without queues.
2. **Phase 2: Standard QoS Enforced**: Medical guaranteed Queue 1; IoT throttled to Queue 2 (1 Mbps).
3. **Phase 3: Code Blue Preemption Active**: ICU telemetry boosted to Queue 3; Admin and Guest throttled/dropped.

The script automatically outputs `qos_results.csv` and renders `qos_comparison.png`, which is automatically copied to your macOS host!

---

## 🎮 Interactive Arrow-Key Flow Console

Launch the interactive curses terminal console from Mac:
```bash
./scripts/run_multipass.sh console
```
Features:
* Browse live flows across all 6 switches.
* Trigger / Resolve **Code Blue** emergency states with arrow keys.
* Inspect quarantined IoMT devices and release remediated hosts.
* Inspect **Fast Failover** OpenFlow 1.3 Group tables.
* Add and delete preset or custom OpenFlow rules.
* View host IP and subnet cheat sheets.
