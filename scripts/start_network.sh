#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Automatically find Python binary with Ryu support
if [ -x "/home/ubuntu/venv/bin/python3" ]; then
    PYTHON_CMD="/home/ubuntu/venv/bin/python3"
elif [ -n "$VIRTUAL_ENV" ] && [ -x "$VIRTUAL_ENV/bin/python3" ]; then
    PYTHON_CMD="$VIRTUAL_ENV/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

export PYTHONPATH="/usr/lib/python3/dist-packages:$REPO_ROOT:$PYTHONPATH"

# Cleanup any lingering mininet sessions
echo "[*] Cleaning up previous Mininet sessions..."
sudo mn -c >/dev/null 2>&1 || true

echo "[*] Starting Ryu Controller with REST API & WSGI on 0.0.0.0:8080..."
# Bind wsapi-host to 0.0.0.0 so the REST endpoints are accessible from the macOS host via Multipass IP
$PYTHON_CMD -m ryu.cmd.manager \
    --wsapi-host 0.0.0.0 \
    --wsapi-port 8080 \
    "$REPO_ROOT/controller/hospital_controller.py" \
    ryu.app.ofctl_rest \
    > "$SCRIPT_DIR/ryu_controller.log" 2>&1 &
RYU_PID=$!

trap 'echo "[*] Terminating Ryu Controller (PID $RYU_PID)..."; kill $RYU_PID 2>/dev/null || true' EXIT INT TERM

echo "[+] Ryu Controller started (PID: $RYU_PID)"
echo "[*] Waiting 4 seconds for controller and OpenFlow listener to initialize..."
sleep 4

echo "[*] Launching Hospital Mininet Topology with Fast Failover and QoS Queues..."
sudo env PYTHONPATH="$PYTHONPATH" "$PYTHON_CMD" "$REPO_ROOT/topology/hospital_topo.py"

echo "[*] Mininet session terminated."
