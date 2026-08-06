# Hospital SDN Project

This project implements a Software-Defined Network (SDN) for a hospital environment. It uses **Mininet** to simulate the network topology and **Ryu** as the OpenFlow controller to manage network policies, QoS, and security.

> **Note on launching Ryu**: All scripts launch the controller with
> `python -m ryu.cmd.manager` (not `ryu-manager`). If your `python`
> binary is called `python3`, replace it accordingly (or `alias python=python3`).

## Architecture

The network is divided into several logical zones (VLANs equivalent):
*   **Datacenter**: Hosts internal servers (Medical DB, Admin DB).
*   **Medical Department**: Doctors and Nurses (Requires access to Medical DB).
*   **Admin Department**: Management and Billing (Requires access to Admin DB).
*   **IoT/Medical Devices**: MRI machines, monitors (Strictly isolated, only accesses Medical DB).
*   **Guest WiFi**: Public internet access for visitors (Isolated from all internal hospital networks).

> **Network model**: All hosts share a flat L2 fabric on `10.0.0.0/16` (every host
> uses a `/16` netmask). Zones are **not** separated by IP routing — they are
> enforced purely by the SDN flow rules installed by the controller (see below).
> Because the fabric is flat, traffic between any two hosts actually reaches the
> switches, where the firewall drops and QoS queueing take effect. This is what
> makes the `Network is unreachable` problem disappear without adding a router.

## Security & QoS Policies

The Ryu controller enforces the following rules using OpenFlow and OVS Queues:
1.  **Guest Isolation**: Guests cannot access any internal hospital host or server. They can only communicate with other external entities (simulated by allowing Guest-to-Guest communication only).
2.  **IoT Isolation & QoS**: IoT devices cannot access Admin or Guest networks. They can only communicate with the Medical Datacenter. Because they are low-priority devices, their bandwidth is strictly throttled to 1Mbps max using OVS queues.
3.  **Department Access & QoS**: Medical staff can access the Medical server and are assigned High Priority bandwidth (Queue 1) to ensure critical data transfers quickly. Admin staff can access the Admin server.

## Prerequisites

*   Ubuntu/Debian-based Linux distribution (recommended)
*   Mininet
*   Ryu SDN Framework
*   Python 3 (with `pandas` and `matplotlib` for charts)
*   `tcpdump`, `iperf`, `curl` (for traffic capture and REST demos)

### Installation

```bash
# Install Mininet
sudo apt-get update
sudo apt-get install mininet

# Install Python requirements
pip3 install -r requirements.txt

# Tools used by the experiment/demo scripts
sudo apt-get install -y tcpdump iperf curl
```

## Running the Project

You can run the project manually or use the provided startup script.

### Using the Startup Script

```bash
# Make the scripts executable
chmod +x scripts/start_network.sh scripts/demo_manual_flows.sh

# Run the script (requires sudo)
sudo ./scripts/start_network.sh
```

The script launches the controller via `python -m ryu.cmd.manager` with the
Ryu REST API app (`ryu.app.ofctl_rest`, listens on port **8080**) so you can
insert/delete flow rules manually during the demo.

## Rubric Point 2: Flow Rule Implementation (manual insertion via controller API)

The controller installs **proactive** flow rules when each switch connects
(`install_firewall_rules`, `install_qos_rules` in `controller/hospital_controller.py`).

To demonstrate **manual rule insertion** at runtime, use the REST API that
`ryu.app.ofctl_rest` exposes on port 8080:

*   List flows on switch 1 (core):
    ```bash
    curl -s http://127.0.0.1:8080/stats/flow/1 | python3 -m json.tool
    ```
*   Insert a DROP rule (block `h_doc1` 10.0.2.11 -> `h_med_srv` 10.0.1.10):
    ```bash
    curl -s -X POST -d '{
      "dpid": 1,
      "priority": 50,
      "match": {"eth_type": 2048, "ipv4_src": "10.0.2.11", "ipv4_dst": "10.0.1.10"},
      "actions": []
    }' http://127.0.0.1:8080/stats/flowentry/add
    ```
*   Delete it again:
    ```bash
    curl -s -X POST -d '{
      "dpid": 1,
      "priority": 50,
      "match": {"eth_type": 2048, "ipv4_src": "10.0.2.11", "ipv4_dst": "10.0.1.10"}
    }' http://127.0.0.1:8080/stats/flowentry/delete
    ```
*   Verify in OVS directly:
    ```bash
    sudo ovs-ofctl -O OpenFlow13 dump-flows s1
    ```

For a guided, interactive version of this demo run `scripts/demo_manual_flows.sh`
(a scripted walkthrough with pauses).

For an **interactive arrow-key console**, run `scripts/flow_console.py` in a
separate terminal while the controller and Mininet are up:

```bash
python3 scripts/flow_console.py
```

It lets you browse live flows, add/delete preset rules (drop rules + QoS
`set_queue` rules), add fully custom rules, and view a host/zone cheat-sheet —
all through the REST API (Up/Down to move, Enter to select, `q` to go back).

## Automated QoS Evaluation (Lab Rubric Points 3, 4, 5)

To automatically test the QoS policies, capture packets, and generate
before/after performance charts:

1.  **Run the Experiment Script**:
    ```bash
    sudo python3 scripts/run_experiments.py
    ```
    *This starts the network, measures a BASELINE (no QoS queues), applies the
    OVS QoS queues, re-measures with QoS active, and runs `tcpdump` during both
    phases. iperf runs in reverse mode (`-R`) so traffic flows from the server
    through the shaped egress port on `s2`, exactly where the queues are applied.*

2.  **Generate the Charts**:
    ```bash
    python3 scripts/plot_results.py
    ```
    *Reads `qos_results.csv` and generates `qos_comparison.png`, a grouped
    Before/After bar chart.*

3.  **Check Packet Captures**:
    The script saves two pcap files in `pcap/`:
    *   `baseline_capture.pcap` (during the unshaped phase)
    *   `qos_capture.pcap` (during QoS enforcement)
    These prove traffic monitoring during QoS enforcement. Analyze them with
    `tshark -r pcap/qos_capture.pcap` or Wireshark.

## Testing the Firewall Policies Manually

Once the Mininet CLI (`mininet>`) is available, you can run tests to verify the policies:

*   **Test basic connectivity:**
    ```
    mininet> pingall
    ```
    *Expectation*: Not all pings should succeed due to our firewall rules.

*   **Test Medical access to Medical Server (Should Succeed):**
    ```
    mininet> h_doc1 ping -c 3 h_med_srv
    ```

*   **Test Admin access to Admin Server (Should Succeed):**
    ```
    mininet> h_admin1 ping -c 3 h_adm_srv
    ```

*   **Test Guest isolation (Should Fail to reach internal servers):**
    ```
    mininet> h_guest1 ping -c 3 h_med_srv
    mininet> h_guest1 ping -c 3 h_admin1
    ```

*   **Test IoT isolation (Should Succeed to Med Srv, Fail to Admin):**
    ```
    mininet> h_mri1 ping -c 3 h_med_srv
    mininet> h_mri1 ping -c 3 h_adm_srv
    ```

## How to Change Things (live demo cheat sheet)

*   **Change a bandwidth limit / queue rate**
    Edit `configure_qos()` in `topology/hospital_topo.py` (e.g. line with
    `other-config:max-rate=1000000` = 1 Mbps for the IoT queue). Rates are in
    bits/sec. `min-rate` guarantees, `max-rate` caps.

*   **Add/remove firewall or QoS flow rules**
    Edit `install_firewall_rules()` / `install_qos_rules()` in
    `controller/hospital_controller.py`. Match fields (e.g. `ipv4_src`,
    `ipv4_dst`), priorities, and actions are all plain Ryu code. Higher
    priority wins (firewall drops=10, QoS=20, L2 learning=1, table-miss=0).

*   **Which switch gets QoS flows**
    Change `if datapath.id == 2:` in `switch_features_handler`
    (`controller/hospital_controller.py`).

*   **Point QoS at a different traffic direction**
    The rules match `ipv4_dst` and shape egress on `s2` port 1. To shape the
    opposite direction, add rules matching `ipv4_src` (and make sure the
    corresponding OVS port has queues via `configure_qos()`).

*   **Test duration / iperf options**
    Edit `run_iperf()` / the `duration` argument in `scripts/run_experiments.py`
    (default `-t 5`). Add `-b` to test UDP bitrate limits instead of TCP.

*   **Controller launch command**
    All scripts use `python -m ryu.cmd.manager`. Change the `RYU_CMD` constant
    in `run_experiments.py` or the command in `start_network.sh` / the manual
    instructions if your environment differs.
