#!/bin/bash
# ==============================================================================
# Setup Script: Prepare Ubuntu Multipass VM for Hospital SDN on macOS
# ==============================================================================

set -e

VM_NAME="${1:-refined-pup}"
MEMORY="2G"
CPUS="2"
DISK="15G"

echo "=================================================================="
echo "  Hospital SDN - Multipass Environment Setup"
echo "=================================================================="

# 1. Check if Multipass is installed on macOS
if ! command -v multipass >/dev/null 2>&1; then
    echo "[-] Error: Multipass is not installed."
    echo "    Install it on your Mac with: brew install --cask multipass"
    echo "    or download from: https://multipass.run/"
    exit 1
fi

echo "[+] Multipass detected: $(multipass version | head -n 1)"

# 2. Check if the VM instance exists
VM_STATUS=$(multipass list 2>/dev/null | awk -v vm="$VM_NAME" '$1 == vm {print $2}')

if [ -z "$VM_STATUS" ]; then
    echo "[*] VM '$VM_NAME' does not exist. Creating new Ubuntu LTS instance..."
    multipass launch --name "$VM_NAME" --cpus "$CPUS" --memory "$MEMORY" --disk "$DISK"
    echo "[+] Instance '$VM_NAME' created and started."
elif [ "$VM_STATUS" != "Running" ]; then
    echo "[*] Starting existing instance '$VM_NAME'..."
    multipass start "$VM_NAME"
    echo "[+] Instance '$VM_NAME' is now running."
else
    echo "[+] Instance '$VM_NAME' is already running."
fi

VM_IP=$(multipass info "$VM_NAME" | awk '/IPv4:/ {print $2}')
echo "[+] Instance IPv4: $VM_IP"

# 3. Install packages in VM
echo "[*] Verifying & installing system dependencies in VM (mininet, openvswitch, tools)..."
multipass exec "$VM_NAME" -- sudo apt-get update -y
multipass exec "$VM_NAME" -- sudo apt-get install -y mininet openvswitch-switch tcpdump iperf curl python3-pip python3-venv

# 4. Set up Python virtual environment
echo "[*] Setting up Python environment in VM..."
multipass exec "$VM_NAME" -- bash -c "
    if [ ! -d ~/venv ]; then
        python3 -m venv --system-site-packages ~/venv
    fi
    ~/venv/bin/pip install --upgrade pip
    ~/venv/bin/pip install ryu flask pandas matplotlib requests
"

# 5. Sync the repository into VM
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/sync_to_vm.sh" "$VM_NAME"

echo
echo "=================================================================="
echo "  Multipass VM '$VM_NAME' is fully configured and ready!"
echo "  VM IP Address: $VM_IP"
echo "  Run experiments using: ./scripts/run_multipass.sh [command]"
echo "=================================================================="
