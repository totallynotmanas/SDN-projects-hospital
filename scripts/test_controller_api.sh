#!/bin/bash
# ==============================================================================
# Integration test for Hospital Controller REST API and Ryu WSGI endpoints
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Find python
if [ -x "/home/ubuntu/venv/bin/python3" ]; then
    PYTHON_CMD="/home/ubuntu/venv/bin/python3"
else
    PYTHON_CMD="python3"
fi

export PYTHONPATH="/usr/lib/python3/dist-packages:$REPO_ROOT:$PYTHONPATH"

# Stop any running Ryu instances
pkill -f 'ryu.cmd.manager' 2>/dev/null || true
sleep 1

echo "[*] Launching Ryu with HospitalController & ofctl_rest..."
nohup $PYTHON_CMD -m ryu.cmd.manager \
    --wsapi-host 0.0.0.0 \
    --wsapi-port 8080 \
    "$REPO_ROOT/controller/hospital_controller.py" \
    ryu.app.ofctl_rest \
    > "$SCRIPT_DIR/ryu_controller.log" 2>&1 &
RYU_PID=$!
echo "[+] Controller PID: $RYU_PID"

cleanup() {
    echo "[*] Stopping controller (PID $RYU_PID)..."
    kill $RYU_PID 2>/dev/null || true
}
trap cleanup EXIT

echo "[*] Waiting 5 seconds for Ryu WSGI server to initialize..."
sleep 5

echo
echo "=========================================================="
echo "1. Testing /hospital/emergency (GET)"
echo "=========================================================="
curl -s http://127.0.0.1:8080/hospital/emergency
echo

echo
echo "=========================================================="
echo "2. Testing /hospital/emergency (POST CODE_BLUE)"
echo "=========================================================="
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"status": "CODE_BLUE", "unit": "ICU_Room_1"}' \
    http://127.0.0.1:8080/hospital/emergency
echo

echo
echo "=========================================================="
echo "3. Testing /hospital/emergency (POST RESOLVED)"
echo "=========================================================="
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"status": "RESOLVED"}' \
    http://127.0.0.1:8080/hospital/emergency
echo

echo
echo "=========================================================="
echo "4. Testing /hospital/quarantine (GET)"
echo "=========================================================="
curl -s http://127.0.0.1:8080/hospital/quarantine
echo

echo
echo "=========================================================="
echo "5. Testing /hospital/quarantine (POST ISOLATE)"
echo "=========================================================="
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"host": "10.0.4.11", "action": "ISOLATE"}' \
    http://127.0.0.1:8080/hospital/quarantine
echo

echo
echo "=========================================================="
echo "6. Testing /hospital/quarantine (POST RELEASE)"
echo "=========================================================="
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"host": "10.0.4.11", "action": "RELEASE"}' \
    http://127.0.0.1:8080/hospital/quarantine
echo

echo
echo "=========================================================="
echo "7. Testing /hospital/failover (GET)"
echo "=========================================================="
curl -s http://127.0.0.1:8080/hospital/failover
echo

echo
echo "[+] All Controller API endpoints responded successfully!"
