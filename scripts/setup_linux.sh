#!/bin/bash
# ==============================================================================
# Setup Script: Native Linux (Ubuntu/Debian) for Hospital SDN
# ==============================================================================
set -e

echo "=================================================================="
echo "  Hospital SDN - Native Linux Setup (Ubuntu/Debian)"
echo "=================================================================="

# Check root / sudo
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

echo "[*] Updating package repositories..."
$SUDO apt-get update -y

echo "[*] Installing Mininet, Open vSwitch, networking utilities, and Python tools..."
$SUDO apt-get install -y mininet openvswitch-switch tcpdump iperf curl iproute2 python3-pip python3-venv python3-dev

echo "[*] Ensuring Open vSwitch daemon is active..."
$SUDO systemctl enable --now openvswitch-switch || $SUDO service openvswitch-switch start

# Setup Python virtual environment with system site packages (enables mininet Python bindings)
VENV_DIR="$HOME/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating Python virtual environment at $VENV_DIR..."
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

echo "[*] Installing Python dependencies (Ryu, Flask, Pandas, Matplotlib, Requests)..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install ryu flask pandas matplotlib requests

echo "[*] Setting execution permissions for scripts..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR"/*.sh "$SCRIPT_DIR"/*.py 2>/dev/null || true

echo ""
echo "=================================================================="
echo "  [+] Native Linux Setup Completed Successfully!"
echo "=================================================================="
echo "  To start the interactive network: sudo ./scripts/start_network.sh"
echo "  To run Code Blue Demo:            sudo $VENV_DIR/bin/python3 scripts/demo_code_blue.py"
echo "  To run IoMT Quarantine Demo:      sudo $VENV_DIR/bin/python3 scripts/demo_quarantine.py"
echo "  To run Fast Failover Demo:        sudo $VENV_DIR/bin/python3 scripts/demo_fast_failover.py"
echo "  To run 12-Point Test Suite:       sudo $VENV_DIR/bin/python3 scripts/test_mininet_connectivity.py"
echo "  To run Full QoS Benchmarks:       sudo $VENV_DIR/bin/python3 scripts/run_experiments.py"
echo "  To launch Interactive Console:    $VENV_DIR/bin/python3 scripts/flow_console.py"
echo "=================================================================="
