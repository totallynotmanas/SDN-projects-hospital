#!/bin/bash
# ==============================================================================
# Fast Code Sync to Multipass VM
# Streams repository files to ~/hospital-sdn inside the VM via tar over multipass exec.
# Uses COPYFILE_DISABLE=1 to omit AppleDouble metadata files and preserves execution bits.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

VM_NAME="${1:-refined-pup}"

# Check if multipass exists
if ! command -v multipass >/dev/null 2>&1; then
    echo "[-] Error: multipass is not installed on this Mac."
    exit 1
fi

# Check if target VM is running
VM_STATE=$(multipass list 2>/dev/null | awk -v vm="$VM_NAME" '$1 == vm {print $2}')
if [ "$VM_STATE" != "Running" ]; then
    RUNNING_VM=$(multipass list 2>/dev/null | awk '$2 == "Running" {print $1; exit}')
    if [ -n "$RUNNING_VM" ]; then
        VM_NAME="$RUNNING_VM"
        echo "[*] Using active Multipass instance: $VM_NAME"
    else
        echo "[-] Error: Multipass instance '$VM_NAME' is not running."
        echo "    Start it with: multipass start $VM_NAME"
        exit 1
    fi
fi

echo "[*] Syncing code from Mac to Multipass VM ($VM_NAME:~/hospital-sdn)..."

# Ensure target directory exists in VM and clean any previous AppleDouble files
multipass exec "$VM_NAME" -- mkdir -p /home/ubuntu/hospital-sdn

# Stream clean tar directly into VM
cd "$REPO_ROOT"
COPYFILE_DISABLE=1 tar -czf - \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='pcap/*.pcap' \
    . | multipass exec "$VM_NAME" -- tar --warning=no-unknown-keyword -xzf - -C /home/ubuntu/hospital-sdn

# Remove any existing ._* files if present and ensure executable permissions
multipass exec "$VM_NAME" -- bash -c "rm -f /home/ubuntu/hospital-sdn/._* /home/ubuntu/hospital-sdn/*[./]* 2>/dev/null || true"
multipass exec "$VM_NAME" -- bash -c "chmod +x /home/ubuntu/hospital-sdn/scripts/*.sh /home/ubuntu/hospital-sdn/scripts/*.py 2>/dev/null || true"

echo "[+] Sync completed successfully to /home/ubuntu/hospital-sdn on $VM_NAME!"
