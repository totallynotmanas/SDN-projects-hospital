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

## 💻 Operating System Guides: Linux, macOS & Windows

Mininet relies on Linux kernel primitives (network namespaces, Open vSwitch kernel modules, and virtual ethernet `veth` pairs). Below are the dedicated setup and execution guides for **Native Linux**, **macOS** (via Multipass), and **Windows** (via Multipass, WSL2, or VM).

---

### 🐧 1. Native Linux (Ubuntu 22.04 / 24.04 LTS or Debian)

On Linux, Mininet and Ryu run natively on bare metal with direct kernel Open vSwitch integration.

#### One-Step Automated Setup
From your terminal in the repository root:
```bash
sudo ./scripts/setup_linux.sh
```
*This installs Mininet, Open vSwitch, tcpdump, iperf, creates `~/venv` with `--system-site-packages` (so the system Mininet library is accessible), installs Ryu, Flask, Pandas, and Matplotlib, and makes all scripts executable.*

#### Manual Setup (Alternative)
```bash
sudo apt-get update -y
sudo apt-get install -y mininet openvswitch-switch tcpdump iperf curl iproute2 python3-pip python3-venv python3-dev
sudo systemctl enable --now openvswitch-switch
python3 -m venv --system-site-packages ~/venv
~/venv/bin/pip install --upgrade pip
~/venv/bin/pip install ryu flask pandas matplotlib requests
```

#### Running on Linux
```bash
# 1. Start the interactive Mininet network + Ryu controller:
sudo ./scripts/start_network.sh

# 2. Run the standalone live demos with real network traffic:
sudo ~/venv/bin/python3 scripts/demo_code_blue.py
sudo ~/venv/bin/python3 scripts/demo_quarantine.py
sudo ~/venv/bin/python3 scripts/demo_fast_failover.py

# 3. Run the 12-point automated verification test suite:
sudo ~/venv/bin/python3 scripts/test_mininet_connectivity.py

# 4. Run full 3-phase QoS evaluation benchmarks (generates qos_comparison.png):
sudo ~/venv/bin/python3 scripts/run_experiments.py

# 5. Launch the interactive curses Flow Console:
~/venv/bin/python3 scripts/flow_console.py
```

---

### 🍏 2. macOS (via Multipass Ubuntu VM)

Because macOS uses the Darwin kernel, Mininet is executed inside a lightweight, headless Ubuntu LTS Multipass VM.

#### Prerequisites on Mac
Install Multipass via Homebrew or official installer:
```bash
brew install --cask multipass
```
*(Or download from [multipass.run](https://multipass.run/))*

#### One-Time VM Provisioning
```bash
./scripts/setup_multipass.sh
```
*Creates the Ubuntu LTS instance, provisions Open vSwitch, Mininet, Ryu, and Python packages, and syncs the repository.*

#### One-Click macOS Commands
Use the `./scripts/run_multipass.sh` wrapper from your Mac terminal:
```bash
# Display VM IP address and reachable REST endpoints
./scripts/run_multipass.sh info

# Sync code to VM and start interactive Mininet session & Ryu
./scripts/run_multipass.sh network

# Run the Code Blue Dynamic QoS Preemption demo (live iperf measurements)
./scripts/run_multipass.sh codeblue

# Run the IoMT Anomaly Quarantine demo (live threat isolation)
./scripts/run_multipass.sh quarantine

# Run the Sub-Millisecond Fast Failover demo (cable break simulation)
./scripts/run_multipass.sh failover

# Run the 12-test automated integration suite
./scripts/run_multipass.sh test

# Run full QoS benchmarks & automatically copy qos_comparison.png to Mac host
./scripts/run_multipass.sh experiments

# Launch the interactive arrow-key Flow Console
./scripts/run_multipass.sh console

# Open an interactive bash shell in the VM
./scripts/run_multipass.sh shell
```

#### Accessing Controller REST API from Mac Terminal / Browser
```bash
VM_IP=$(multipass info refined-pup | awk '/IPv4:/ {print $2}')

# Query Code Blue Emergency status
curl -s http://$VM_IP:8080/hospital/emergency | python3 -m json.tool

# Query IoMT Quarantine registry
curl -s http://$VM_IP:8080/hospital/quarantine | python3 -m json.tool

# Query Fast Failover configuration
curl -s http://$VM_IP:8080/hospital/failover | python3 -m json.tool

# Dump live flows on Core switch s1
curl -s http://$VM_IP:8080/stats/flow/1 | python3 -m json.tool
```

---

### 🪟 3. Windows (Multipass, WSL 2, or VirtualBox)

Windows users have three robust options depending on their preferred workflow.

#### Option A: Multipass for Windows (Recommended — 1-to-1 Parity with Mac)
Multipass on Windows provides full native Linux kernel Open vSwitch and Linux-HTB QoS support, with zero manual Linux kernel configuration.

1. **Install Multipass on Windows**:
   Open PowerShell as Administrator and run:
   ```powershell
   winget install Canonical.Multipass
   ```
   *(Or download the installer from [multipass.run](https://multipass.run/))*

2. **One-Click Commands via PowerShell**:
   Open PowerShell in the cloned repository directory:
   ```powershell
   # Display VM IP and REST endpoints
   .\scripts\run_multipass.ps1 info

   # Start interactive Mininet & Ryu controller
   .\scripts\run_multipass.ps1 network

   # Run feature demonstrations with live traffic
   .\scripts\run_multipass.ps1 codeblue
   .\scripts\run_multipass.ps1 quarantine
   .\scripts\run_multipass.ps1 failover

   # Run 12-test automated verification suite
   .\scripts\run_multipass.ps1 test

   # Run QoS benchmarks & automatically copy chart & CSV to Windows folder
   .\scripts\run_multipass.ps1 experiments

   # Launch interactive Flow Console
   .\scripts\run_multipass.ps1 console

   # Open interactive bash shell inside the VM
   .\scripts\run_multipass.ps1 shell
   ```
   *(Note: If using Git Bash on Windows, you can also run `./scripts/run_multipass.sh <command>` directly!)*

#### Option B: Standalone Ubuntu VM (VirtualBox / VMware Player)
1. Download [Ubuntu 24.04 LTS Desktop/Server ISO](https://ubuntu.com/download/desktop).
2. Create a VM in VirtualBox or VMware Player (2 vCPUs, 3 GB RAM, 15 GB disk, Bridged or NAT network).
3. Clone this repository inside the VM and run:
   ```bash
   sudo ./scripts/setup_linux.sh
   ```
4. Run all tests and demos using the standard [Native Linux commands](#-1-native-linux-ubuntu-2204--2404-lts-or-debian).

#### Option C: Windows Subsystem for Linux (WSL 2)
> [!NOTE]
> Standard WSL 2 distributions use a specialized Microsoft kernel that omits standard Open vSwitch kernel modules (`openvswitch.ko`).
> * If using WSL 2, you can either:
>   1. Run Mininet with userspace switching: `mininet --switch user` (functional for L2 forwarding, but lacks kernel-level Linux-HTB hardware queues).
>   2. Or install Multipass on Windows (Option A) or a VirtualBox VM (Option B) for 100% hardware-accurate kernel OVS and HTB QoS performance.

---

## 🩺 Step-by-Step Feature Demos

### Demo 1: "Code Blue" Event-Driven Dynamic QoS Preemption

Run the interactive walkthrough with live iperf traffic:
* **Linux (Native)**:
  ```bash
  sudo ~/venv/bin/python3 scripts/demo_code_blue.py
  ```
* **macOS (Multipass)**:
  ```bash
  ./scripts/run_multipass.sh codeblue
  ```
* **Windows (PowerShell)**:
  ```powershell
  .\scripts\run_multipass.ps1 codeblue
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
* **Linux (Native)**:
  ```bash
  sudo ~/venv/bin/python3 scripts/demo_quarantine.py
  ```
* **macOS (Multipass)**:
  ```bash
  ./scripts/run_multipass.sh quarantine
  ```
* **Windows (PowerShell)**:
  ```powershell
  .\scripts\run_multipass.ps1 quarantine
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
* **Linux (Native)**:
  ```bash
  sudo ~/venv/bin/python3 scripts/demo_fast_failover.py
  ```
* **macOS (Multipass)**:
  ```bash
  ./scripts/run_multipass.sh failover
  ```
* **Windows (PowerShell)**:
  ```powershell
  .\scripts\run_multipass.ps1 failover
  ```
*Shows Group Table 1 (`OFPGT_FF`) with Bucket 1 (`watch_port=1`) and Bucket 2 (`watch_port=2`). Cuts primary interface `s2-eth1` and demonstrates uninterrupted ping delivery over backup interface `s2-eth2`.*

---

## 🧪 Comprehensive Automated Test Suite (12/12 Passing)

Run the complete integration suite across your platform:
* **Linux (Native)**:
  ```bash
  sudo ~/venv/bin/python3 scripts/test_mininet_connectivity.py
  ```
* **macOS (Multipass)**:
  ```bash
  ./scripts/run_multipass.sh test
  ```
* **Windows (PowerShell)**:
  ```powershell
  .\scripts\run_multipass.ps1 test
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
* **Linux (Native)**:
  ```bash
  sudo ~/venv/bin/python3 scripts/run_experiments.py
  ```
  *(Generates `qos_results.csv` and `qos_comparison.png` directly in your project root!)*
* **macOS (Multipass)**:
  ```bash
  ./scripts/run_multipass.sh experiments
  ```
* **Windows (PowerShell)**:
  ```powershell
  .\scripts\run_multipass.ps1 experiments
  ```

This runs three benchmark phases:
1. **Phase 1: Baseline (Unshaped)**: Measures baseline throughput without queues.
2. **Phase 2: Standard QoS Enforced**: Medical guaranteed Queue 1; IoT throttled to Queue 2 (1 Mbps).
3. **Phase 3: Code Blue Preemption Active**: ICU telemetry boosted to Queue 3; Admin and Guest throttled/dropped.

The runner automatically saves `qos_results.csv` and renders `qos_comparison.png` into your local directory.

---

## 🎮 Interactive Arrow-Key Flow Console

Launch the interactive curses terminal console:
* **Linux (Native)**:
  ```bash
  ~/venv/bin/python3 scripts/flow_console.py
  ```
* **macOS (Multipass)**:
  ```bash
  ./scripts/run_multipass.sh console
  ```
* **Windows (PowerShell)**:
  ```powershell
  .\scripts\run_multipass.ps1 console
  ```

Features:
* Browse live flows across all 6 switches.
* Trigger / Resolve **Code Blue** emergency states with arrow keys.
* Inspect quarantined IoMT devices and release remediated hosts.
* Inspect **Fast Failover** OpenFlow 1.3 Group tables.
* Add and delete preset or custom OpenFlow rules.
* View host IP and subnet cheat sheets.

