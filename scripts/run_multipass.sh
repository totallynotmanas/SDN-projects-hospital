#!/bin/bash
# ==============================================================================
# Multipass Runner for macOS: Hospital SDN Project
# One-stop utility to run Mininet, Ryu, and all demos from your Mac.
#
# Usage:
#   ./scripts/run_multipass.sh network      # Start Ryu & Mininet interactive CLI
#   ./scripts/run_multipass.sh codeblue     # Run Code Blue dynamic QoS demo
#   ./scripts/run_multipass.sh quarantine   # Run IoMT Anomaly Quarantine demo
#   ./scripts/run_multipass.sh failover     # Run Fast Failover resilience demo
#   ./scripts/run_multipass.sh console      # Launch curses Flow Console
#   ./scripts/run_multipass.sh experiments  # Run automated QoS benchmarks & charts
#   ./scripts/run_multipass.sh shell        # Open interactive shell in VM
#   ./scripts/run_multipass.sh sync         # Sync files from Mac to VM
#   ./scripts/run_multipass.sh info         # Show VM IP and REST endpoints
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

VM_NAME="${MULTIPASS_VM:-refined-pup}"

# Helper to find running VM
detect_vm() {
    local state
    state=$(multipass list 2>/dev/null | awk -v vm="$VM_NAME" '$1 == vm {print $2}')
    if [ "$state" != "Running" ]; then
        local running
        running=$(multipass list 2>/dev/null | awk '$2 == "Running" {print $1; exit}')
        if [ -n "$running" ]; then
            VM_NAME="$running"
        else
            echo "[-] Error: VM '$VM_NAME' is not running."
            echo "    Run './scripts/setup_multipass.sh $VM_NAME' to start it."
            exit 1
        fi
    fi
}

detect_vm
VM_IP=$(multipass info "$VM_NAME" | awk '/IPv4:/ {print $2}')

CMD="${1:-info}"
shift || true

case "$CMD" in
    sync)
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        ;;

    network)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Starting Mininet & Ryu controller in VM..."
        echo "[*] Ryu REST API will be accessible from Mac at: http://$VM_IP:8080"
        echo "[*] Entering interactive Mininet session (type 'exit' or Ctrl+D to quit):"
        multipass exec "$VM_NAME" -- sudo bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            ./scripts/start_network.sh
        "
        ;;

    codeblue)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Running Code Blue Dynamic QoS Preemption Demo..."
        multipass exec "$VM_NAME" -- sudo bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            /home/ubuntu/venv/bin/python3 scripts/demo_code_blue.py $*
        "
        ;;

    quarantine)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Running IoMT Anomaly Quarantine Demo..."
        multipass exec "$VM_NAME" -- sudo bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            /home/ubuntu/venv/bin/python3 scripts/demo_quarantine.py $*
        "
        ;;

    failover)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Running Sub-Millisecond Telemetry Fast Failover Demo..."
        multipass exec "$VM_NAME" -- sudo bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            /home/ubuntu/venv/bin/python3 scripts/demo_fast_failover.py $*
        "
        ;;

    console)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Launching Flow Console in VM..."
        multipass exec "$VM_NAME" -- bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            /home/ubuntu/venv/bin/python3 scripts/flow_console.py
        "
        ;;

    experiments)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Running automated QoS evaluation experiments in VM..."
        multipass exec "$VM_NAME" -- sudo bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            /home/ubuntu/venv/bin/python3 scripts/run_experiments.py
            /home/ubuntu/venv/bin/python3 scripts/plot_results.py
        "
        echo "[*] Fetching generated chart and CSV to Mac host..."
        multipass transfer "$VM_NAME:/home/ubuntu/hospital-sdn/qos_comparison.png" "$REPO_ROOT/qos_comparison.png" 2>/dev/null || true
        multipass transfer "$VM_NAME:/home/ubuntu/hospital-sdn/qos_results.csv" "$REPO_ROOT/qos_results.csv" 2>/dev/null || true
        echo "[+] Results copied to Mac host: qos_comparison.png & qos_results.csv"
        ;;

    shell)
        echo "[*] Opening interactive bash shell in $VM_NAME (/home/ubuntu/hospital-sdn)..."
        multipass exec "$VM_NAME" -- bash -c "cd /home/ubuntu/hospital-sdn && bash"
        ;;

    info)
        echo "=================================================================="
        echo "  Hospital SDN - Multipass Environment Info"
        echo "=================================================================="
        echo "  Target VM Instance: $VM_NAME"
        echo "  VM IPv4 Address:   $VM_IP"
        echo "  Code Path in VM:   /home/ubuntu/hospital-sdn"
        echo ""
        echo "  Direct REST endpoints reachable from Mac terminal:"
        echo "    Emergency State:  curl -s http://$VM_IP:8080/hospital/emergency"
        echo "    Quarantine State: curl -s http://$VM_IP:8080/hospital/quarantine"
        echo "    Failover State:   curl -s http://$VM_IP:8080/hospital/failover"
        echo "    Switch 1 Flows:   curl -s http://$VM_IP:8080/stats/flow/1"
        echo "    Switch 2 Flows:   curl -s http://$VM_IP:8080/stats/flow/2"
        echo ""
        echo "  Available Commands:"
        echo "    ./scripts/run_multipass.sh network      # Start network & CLI"
        echo "    ./scripts/run_multipass.sh codeblue     # Test Code Blue QoS"
        echo "    ./scripts/run_multipass.sh quarantine   # Test IoMT Quarantine"
        echo "    ./scripts/run_multipass.sh failover     # Test Fast Failover"
        echo "    ./scripts/run_multipass.sh console      # Launch Flow Console"
        echo "    ./scripts/run_multipass.sh experiments  # Run full benchmark"
        echo "    ./scripts/run_multipass.sh shell        # Open VM shell"
        echo "    ./scripts/run_multipass.sh sync         # Sync files to VM"
        echo "=================================================================="
        ;;

    test)
        echo "[*] Syncing code to $VM_NAME..."
        "$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"
        echo "[*] Running automated test suite in VM..."
        multipass exec "$VM_NAME" -- sudo bash -c "
            cd /home/ubuntu/hospital-sdn
            export PYTHONPATH=/usr/lib/python3/dist-packages:\$PYTHONPATH
            /home/ubuntu/venv/bin/python3 scripts/test_mininet_connectivity.py
        "
        ;;

    help|-h|--help)
        echo "Usage: ./scripts/run_multipass.sh [command]"
        echo ""
        echo "Commands:"
        echo "  network      Start Mininet topology & OpenFlow controller interactively"
        echo "  codeblue     Trigger and verify Code Blue emergency preemption"
        echo "  quarantine   Demonstrate autonomous IoMT anomaly detection & quarantine"
        echo "  failover     Inspect Fast Failover groups and simulate link down"
        echo "  console      Launch interactive curses Flow Console"
        echo "  test         Run the 12-point automated verification test suite"
        echo "  experiments  Run full QoS benchmarking (Baseline vs QoS vs Code Blue)"
        echo "  shell        Open an interactive bash shell in the VM"
        echo "  sync         Sync local files from Mac into the VM"
        echo "  info         Display VM IP, REST endpoints, and connection details"
        ;;

    *)
        echo "[-] Unknown command: $CMD"
        echo "    Usage: ./scripts/run_multipass.sh [network|codeblue|quarantine|failover|console|test|experiments|shell|sync|info]"
        exit 1
        ;;
esac
