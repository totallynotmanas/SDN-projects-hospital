# ==============================================================================
# Hospital SDN Multipass Runner for Windows (PowerShell)
# Provides one-click VM management, atomic code synchronization, and demo execution.
# ==============================================================================

param (
    [Parameter(Position=0)]
    [string]$Command = "info",
    [Parameter(Position=1)]
    [string]$VmName = "hospital-sdn"
)

$ErrorActionPreference = "Stop"

# 1. Verify Multipass installation
if (-not (Get-Command multipass -ErrorAction SilentlyContinue)) {
    Write-Host "[-] Error: Multipass is not installed on Windows." -ForegroundColor Red
    Write-Host "    Install via PowerShell: winget install Canonical.Multipass" -ForegroundColor Yellow
    Write-Host "    Or download from: https://multipass.run/" -ForegroundColor Yellow
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Function to ensure VM exists and is running
function Ensure-VM {
    param([string]$Name)
    $list = multipass list 2>$null
    $found = $false
    $running = $false

    foreach ($line in $list -split "`n") {
        $parts = $line.Trim() -split "\s+"
        if ($parts[0] -eq $Name) {
            $found = $true
            if ($parts[1] -eq "Running") { $running = $true }
            break
        }
    }

    if (-not $found) {
        # Check if fallback VM exists (e.g. refined-pup)
        foreach ($fallback in @("refined-pup", "hospital-sdn")) {
            foreach ($line in $list -split "`n") {
                $parts = $line.Trim() -split "\s+"
                if ($parts[0] -eq $fallback -and $parts[1] -eq "Running") {
                    $script:VmName = $fallback
                    return
                }
            }
        }

        Write-Host "[*] Creating new Ubuntu VM instance '$Name' (2 CPUs, 3GB RAM, 15GB Disk)..." -ForegroundColor Cyan
        multipass launch --name $Name --cpus 2 --memory 3G --disk 15G
        Write-Host "[*] Provisioning network packages in VM (Mininet, OVS, Ryu, Python)..." -ForegroundColor Cyan
        multipass exec $Name -- sudo apt-get update -y
        multipass exec $Name -- sudo apt-get install -y mininet openvswitch-switch tcpdump iperf curl python3-pip python3-venv
        multipass exec $Name -- bash -c "python3 -m venv --system-site-packages ~/venv && ~/venv/bin/pip install --upgrade pip && ~/venv/bin/pip install ryu flask pandas matplotlib requests"
    } elseif (-not $running) {
        Write-Host "[*] Starting existing instance '$Name'..." -ForegroundColor Cyan
        multipass start $Name
    }
}

# Function to sync repository from Windows to VM
function Sync-Code {
    param([string]$Name)
    Write-Host "[*] Syncing project files to VM ($Name:~/hospital-sdn)..." -ForegroundColor Cyan
    multipass exec $Name -- mkdir -p /home/ubuntu/hospital-sdn

    # Check for tar.exe in Windows System32
    if (Get-Command tar -ErrorAction SilentlyContinue) {
        Push-Location $RepoRoot
        try {
            tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' -czf - . | multipass exec $Name -- tar --warning=no-unknown-keyword -xzf - -C /home/ubuntu/hospital-sdn
        } finally {
            Pop-Location
        }
    } else {
        # Fallback to multipass transfer
        multipass transfer -r "$RepoRoot/*" "$Name`:/home/ubuntu/hospital-sdn"
    }

    multipass exec $Name -- sudo bash -c "chmod +x /home/ubuntu/hospital-sdn/scripts/*.sh /home/ubuntu/hospital-sdn/scripts/*.py 2>/dev/null || true"
    Write-Host "[+] Code synchronization completed!" -ForegroundColor Green
}

Ensure-VM -Name $VmName

$VmIp = (multipass info $VmName 2>$null | Select-String "IPv4:" | ForEach-Object { ($_ -split "\s+")[1] })

switch ($Command.ToLower()) {
    "sync" {
        Sync-Code -Name $VmName
    }

    "info" {
        Write-Host "==================================================================" -ForegroundColor Cyan
        Write-Host "  Hospital SDN - Windows Multipass Environment" -ForegroundColor Cyan
        Write-Host "==================================================================" -ForegroundColor Cyan
        Write-Host "  Target VM Instance: $VmName"
        Write-Host "  VM IPv4 Address:   $VmIp"
        Write-Host "  Code Path in VM:   /home/ubuntu/hospital-sdn"
        Write-Host ""
        Write-Host "  Direct REST Endpoints (from Windows browser or PowerShell):" -ForegroundColor Yellow
        Write-Host "    Emergency API:   http://$VmIp`:8080/hospital/emergency"
        Write-Host "    Quarantine API:  http://$VmIp`:8080/hospital/quarantine"
        Write-Host "    Failover API:    http://$VmIp`:8080/hospital/failover"
        Write-Host "    Switch 1 Flows:  http://$VmIp`:8080/stats/flow/1"
        Write-Host "    Switch 2 Flows:  http://$VmIp`:8080/stats/flow/2"
        Write-Host ""
        Write-Host "  Available Commands:" -ForegroundColor Yellow
        Write-Host "    .\scripts\run_multipass.ps1 network      # Start interactive Mininet & Ryu"
        Write-Host "    .\scripts\run_multipass.ps1 codeblue     # Test Code Blue QoS Preemption"
        Write-Host "    .\scripts\run_multipass.ps1 quarantine   # Test IoMT Threat Quarantine"
        Write-Host "    .\scripts\run_multipass.ps1 failover     # Test Fast Failover Resilience"
        Write-Host "    .\scripts\run_multipass.ps1 test         # Run 12-test automated verification"
        Write-Host "    .\scripts\run_multipass.ps1 experiments  # Run full benchmark and copy chart"
        Write-Host "    .\scripts\run_multipass.ps1 shell        # Open bash shell in VM"
        Write-Host "    .\scripts\run_multipass.ps1 sync         # Sync files from Windows to VM"
        Write-Host "==================================================================" -ForegroundColor Cyan
    }

    "network" {
        Sync-Code -Name $VmName
        Write-Host "[*] Starting Mininet & Ryu controller in VM..." -ForegroundColor Cyan
        multipass exec $VmName -- sudo bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && ./scripts/start_network.sh"
    }

    "codeblue" {
        Sync-Code -Name $VmName
        Write-Host "[*] Running Code Blue Dynamic QoS Preemption Demo..." -ForegroundColor Cyan
        multipass exec $VmName -- sudo bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && /home/ubuntu/venv/bin/python3 scripts/demo_code_blue.py"
    }

    "quarantine" {
        Sync-Code -Name $VmName
        Write-Host "[*] Running IoMT Anomaly Quarantine Demo..." -ForegroundColor Cyan
        multipass exec $VmName -- sudo bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && /home/ubuntu/venv/bin/python3 scripts/demo_quarantine.py"
    }

    "failover" {
        Sync-Code -Name $VmName
        Write-Host "[*] Running Fast Failover Resilience Demo..." -ForegroundColor Cyan
        multipass exec $VmName -- sudo bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && /home/ubuntu/venv/bin/python3 scripts/demo_fast_failover.py"
    }

    "test" {
        Sync-Code -Name $VmName
        Write-Host "[*] Running 12-Point Automated Integration Suite..." -ForegroundColor Cyan
        multipass exec $VmName -- sudo bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && /home/ubuntu/venv/bin/python3 scripts/test_mininet_connectivity.py"
    }

    "experiments" {
        Sync-Code -Name $VmName
        Write-Host "[*] Running automated QoS evaluation experiments in VM..." -ForegroundColor Cyan
        multipass exec $VmName -- sudo bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && /home/ubuntu/venv/bin/python3 scripts/run_experiments.py"
        Write-Host "[*] Copying qos_comparison.png and qos_results.csv to Windows host..." -ForegroundColor Cyan
        multipass transfer "$VmName`:/home/ubuntu/hospital-sdn/qos_comparison.png" "$RepoRoot\qos_comparison.png"
        multipass transfer "$VmName`:/home/ubuntu/hospital-sdn/qos_results.csv" "$RepoRoot\qos_results.csv"
        Write-Host "[+] Results copied to Windows folder: qos_comparison.png and qos_results.csv" -ForegroundColor Green
    }

    "console" {
        Sync-Code -Name $VmName
        Write-Host "[*] Launching Flow Console in VM..." -ForegroundColor Cyan
        multipass exec $VmName -- bash -c "cd /home/ubuntu/hospital-sdn && export PYTHONPATH=/usr/lib/python3/dist-packages:`$PYTHONPATH && /home/ubuntu/venv/bin/python3 scripts/flow_console.py"
    }

    "shell" {
        Write-Host "[*] Opening bash shell in VM (/home/ubuntu/hospital-sdn)..." -ForegroundColor Cyan
        multipass exec $VmName -- bash -c "cd /home/ubuntu/hospital-sdn && bash"
    }

    default {
        Write-Host "[-] Unknown command: $Command" -ForegroundColor Red
        Write-Host "    Usage: .\scripts\run_multipass.ps1 [network|codeblue|quarantine|failover|test|experiments|console|shell|sync|info]"
        exit 1
    }
}
