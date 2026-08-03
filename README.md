# Hospital SDN Project

This project implements a Software-Defined Network (SDN) for a hospital environment. It uses **Mininet** to simulate the network topology and **Ryu** as the OpenFlow controller to manage network policies and security.

## Architecture

The network is divided into several logical zones (VLANs equivalent):
*   **Datacenter**: Hosts internal servers (Medical DB, Admin DB).
*   **Medical Department**: Doctors and Nurses (Requires access to Medical DB).
*   **Admin Department**: Management and Billing (Requires access to Admin DB).
*   **IoT/Medical Devices**: MRI machines, monitors (Strictly isolated, only accesses Medical DB).
*   **Guest WiFi**: Public internet access for visitors (Isolated from all internal hospital networks).

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

### Installation

```bash
# Install Mininet
sudo apt-get update
sudo apt-get install mininet

# Install Python requirements
pip3 install -r requirements.txt
```

## Running the Project

You can run the project manually or use the provided startup script.

### Using the Startup Script

```bash
# Make the script executable
chmod +x scripts/start_network.sh

# Run the script (requires sudo)
sudo ./scripts/start_network.sh
```

## Automated QoS Evaluation (Lab Rubric Points 3, 4, 5)

To automatically test the QoS policies, capture packets, and generate performance charts:

1.  **Run the Experiment Script**:
    ```bash
    sudo python3 scripts/run_experiments.py
    ```
    *This will start the network, apply QoS queues, run `tcpdump` on the server, and perform `iperf` tests from Medical and IoT hosts to prove the bandwidth limits.*

2.  **Generate the Charts**:
    ```bash
    python3 scripts/plot_results.py
    ```
    *This will read the output CSV and generate `qos_comparison.png`.*

3.  **Check Packet Captures**:
    The automated script saves a `.pcap` file in the `pcap/` directory, proving traffic monitoring during the QoS enforcement.

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
    mininet> h_admin1 ping -c 3 h_admin_srv
    ```

*   **Test Guest isolation (Should Fail to reach internal servers):**
    ```
    mininet> h_guest1 ping -c 3 h_med_srv
    mininet> h_guest1 ping -c 3 h_admin1
    ```

*   **Test IoT isolation (Should Succeed to Med Srv, Fail to Admin):**
    ```
    mininet> h_mri1 ping -c 3 h_med_srv
    mininet> h_mri1 ping -c 3 h_admin_srv
    ```
