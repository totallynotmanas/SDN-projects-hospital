#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Cleanup any existing mininet sessions
sudo mn -c

echo "Starting Ryu Controller (with REST API) in the background..."
# Run the controller via `python -m ryu.cmd.manager`.
# ryu.app.ofctl_rest exposes a REST API (default port 8080) so we can
# insert/delete flow rules manually during the demo.
python -m ryu.cmd.manager "$REPO_ROOT/controller/hospital_controller.py" ryu.app.ofctl_rest \
    > "$SCRIPT_DIR/ryu_controller.log" 2>&1 &
RYU_PID=$!

echo "Ryu Controller started with PID: $RYU_PID"
echo "Waiting 5 seconds for controller to initialize..."
sleep 5

echo "Starting Mininet Topology..."
# Run the topology script
sudo python3 "$REPO_ROOT/topology/hospital_topo.py"

echo "Mininet session ended."
echo "Killing Ryu Controller..."
kill $RYU_PID
echo "Done."
