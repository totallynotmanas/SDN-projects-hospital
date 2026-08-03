#!/bin/bash

# Cleanup any existing mininet sessions
sudo mn -c

echo "Starting Ryu Controller in the background..."
# Run ryu-manager in the background and redirect output to a log file
ryu-manager ../controller/hospital_controller.py > ryu_controller.log 2>&1 &
RYU_PID=$!

echo "Ryu Controller started with PID: $RYU_PID"
echo "Waiting 3 seconds for controller to initialize..."
sleep 3

echo "Starting Mininet Topology..."
# Run the topology script
sudo python3 ../topology/hospital_topo.py

echo "Mininet session ended."
echo "Killing Ryu Controller..."
kill $RYU_PID
echo "Done."
