#!/usr/bin/env python3
"""
Interactive Flow Console for the Hospital SDN project.

Talks to the Ryu controller's REST API (ryu.app.ofctl_rest on port 8080) so
you can add and delete OpenFlow rules at runtime using a simple arrow-key
menu, instead of hand-writing curl commands.

Usage: run it in a separate terminal while the controller AND Mininet are up.

    python3 scripts/flow_console.py

Keys:  Up/Down move the selection, Enter selects, q / Esc goes back.
"""

import curses
import json
import urllib.request

API_BASE = "http://127.0.0.1:8080"
ETH_TYPE_IP = 2048  # 0x0800

# ---------------------------------------------------------------------------
# Reference data (matches topology/hospital_topo.py)
# ---------------------------------------------------------------------------

HOSTS = {
    "h_med_srv": "10.0.1.10",
    "h_adm_srv": "10.0.1.20",
    "h_doc1": "10.0.2.11",
    "h_nurse1": "10.0.2.12",
    "h_admin1": "10.0.3.11",
    "h_hr1": "10.0.3.12",
    "h_mri1": "10.0.4.11",
    "h_monitor1": "10.0.4.12",
    "h_guest1": "10.0.5.11",
    "h_guest2": "10.0.5.12",
    "h_quar": "10.0.99.10",
}

SUBNETS = {
    "Datacenter": "10.0.1.0/24",
    "Medical": "10.0.2.0/24",
    "Admin": "10.0.3.0/24",
    "IoT": "10.0.4.0/24",
    "Guest": "10.0.5.0/24",
}

SWITCHES = [
    ("s1 (core)", 1),
    ("s2 (datacenter)", 2),
    ("s3 (medical)", 3),
    ("s4 (admin)", 4),
    ("s5 (iot)", 5),
    ("s6 (guest)", 6),
]

# ---------------------------------------------------------------------------
# Rule presets
# ---------------------------------------------------------------------------

PRESETS = [
    {
        "name": "Drop h_doc1 -> h_med_srv",
        "dpid": 1,
        "priority": 50,
        "match": {"eth_type": ETH_TYPE_IP, "ipv4_src": "10.0.2.11", "ipv4_dst": "10.0.1.10"},
        "actions": [],
        "check": "h_doc1 ping -c 1 -W 1 h_med_srv   (should now FAIL)",
    },
    {
        "name": "Drop h_mri1 -> h_adm_srv",
        "dpid": 1,
        "priority": 50,
        "match": {"eth_type": ETH_TYPE_IP, "ipv4_src": "10.0.4.11", "ipv4_dst": "10.0.1.20"},
        "actions": [],
        "check": "h_mri1 ping -c 1 -W 1 h_adm_srv   (should now FAIL)",
    },
    {
        "name": "Drop h_guest1 -> h_med_srv",
        "dpid": 1,
        "priority": 50,
        "match": {"eth_type": ETH_TYPE_IP, "ipv4_src": "10.0.5.11", "ipv4_dst": "10.0.1.10"},
        "actions": [],
        "check": "h_guest1 ping -c 1 -W 1 h_med_srv   (already FAILS by default)",
    },
    {
        "name": "Drop h_admin1 -> h_med_srv",
        "dpid": 1,
        "priority": 50,
        "match": {"eth_type": ETH_TYPE_IP, "ipv4_src": "10.0.3.11", "ipv4_dst": "10.0.1.10"},
        "actions": [],
        "check": "h_admin1 ping -c 1 -W 1 h_med_srv   (already FAILS by default)",
    },
    {
        "name": "QoS: Admin subnet -> Queue 1 (high prio) on s2",
        "dpid": 2,
        "priority": 20,
        "match": {"eth_type": ETH_TYPE_IP, "ipv4_dst": "10.0.3.0/24"},
        "actions": [
            {"type": "SET_QUEUE", "queue_id": 1},
            {"type": "OUTPUT", "port": 1},
        ],
        "check": "iperf between an admin host and h_adm_srv",
    },
    {
        "name": "QoS: IoT subnet -> Queue 2 (throttled) on s2",
        "dpid": 2,
        "priority": 20,
        "match": {"eth_type": ETH_TYPE_IP, "ipv4_dst": "10.0.4.0/24"},
        "actions": [
            {"type": "SET_QUEUE", "queue_id": 2},
            {"type": "OUTPUT", "port": 1},
        ],
        "check": "iperf h_mri1 -> h_med_srv should cap around 1 Mbps",
    },
]

# ---------------------------------------------------------------------------
# REST API helpers
# ---------------------------------------------------------------------------


def api_get(path):
    """GET an endpoint and return the parsed JSON."""
    with urllib.request.urlopen(f"{API_BASE}{path}") as resp:
        return json.loads(resp.read().decode())


def api_post(path, payload):
    """POST a JSON payload to an endpoint; return True on HTTP 200."""
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as resp:
        return resp.status == 200


def get_flows(dpid):
    """Return the list of flow dicts currently installed on a switch."""
    data = api_get(f"/stats/flow/{dpid}")
    flows = data.get(str(dpid), [])
    # Some Ryu versions key the flow list by table id instead.
    if isinstance(flows, dict):
        flows = [flow for table in flows.values() for flow in table]
    return flows


def add_flow(dpid, priority, match, actions=None):
    """Insert a flow rule. An empty/None actions list means DROP."""
    payload = {"dpid": dpid, "priority": priority, "match": match}
    if actions is not None:
        payload["actions"] = actions
    return api_post("/stats/flowentry/add", payload)


def delete_flow(dpid, priority, match):
    """Delete matching flow rule(s) on a switch."""
    payload = {"dpid": dpid, "priority": priority, "match": match}
    return api_post("/stats/flowentry/delete", payload)


def _host_name(ip):
    """Return the host name for a known IP, else None."""
    for name, addr in HOSTS.items():
        if addr == ip:
            return name
    return None


def _zone_name(network):
    """Return the zone name for a known subnet network IP, else None."""
    for zone, subnet in SUBNETS.items():
        if subnet.split("/")[0] == network:
            return zone
    return None


def _pretty_addr(value):
    """Resolve an IP/subnet to a host/zone name when known, else raw value."""
    if value is None:
        return "*"
    ip = str(value).split("/")[0]
    return _host_name(ip) or _zone_name(ip) or str(value)


def _describe_actions(flow):
    """Read the action list as the stats API returns it (strings or dicts)."""
    actions = flow.get("actions")
    if isinstance(actions, list):
        return " + ".join(str(a) for a in actions) if actions else "DROP"

    parts = []
    for instruction in flow.get("instructions", []):
        for action in instruction.get("actions", []):
            kind = action.get("type")
            if kind == "OUTPUT":
                parts.append(f"output:{action.get('port')}")
            elif kind == "SET_QUEUE":
                parts.append(f"queue:{action.get('queue_id')}")
    return " + ".join(parts) if parts else "DROP"


def describe_flow(flow):
    """Turn a flow dict from the stats API into a short readable label."""
    match = flow.get("match", {})
    # The REST API reports IPv4 matches under the legacy nw_src/nw_dst keys.
    src = match.get("ipv4_src") or match.get("nw_src")
    dst = match.get("ipv4_dst") or match.get("nw_dst")

    if src is None and dst is None:
        # L2 learning flows match on MACs instead of IPs.
        mac_src = match.get("dl_src")
        mac_dst = match.get("dl_dst")
        if mac_src or mac_dst:
            src, dst = str(mac_src), str(mac_dst)

    label = f"prio {flow.get('priority', 0):<3}  {_pretty_addr(src):>12} -> {_pretty_addr(dst):<12}"
    return f"{label}  [{_describe_actions(flow)}]"


# ---------------------------------------------------------------------------
# Curses UI helpers
# ---------------------------------------------------------------------------

COLOR_READY = False


def init_colors():
    """Enable colors so text renders crisp white instead of terminal-default grey."""
    global COLOR_READY
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)  # body text
    curses.init_pair(2, curses.COLOR_WHITE, -1)  # selection base
    COLOR_READY = True


def with_color(attr):
    """Add the white foreground pair to `attr` when colors are available."""
    return curses.color_pair(1) | attr if COLOR_READY else attr


def arrow_menu(screen, title, options):
    """Show a vertical selectable list; return the chosen option or None."""
    selected = 0
    while True:
        screen.clear()
        screen.addstr(0, 0, title, with_color(curses.A_BOLD))
        for i, option in enumerate(options):
            marker, style = ("> ", curses.A_REVERSE) if i == selected else ("  ", curses.A_NORMAL)
            screen.addstr(i + 1, 0, marker + option[:70], with_color(style))
        screen.addstr(len(options) + 2, 0, "Up/Down move | Enter select | q back", with_color(curses.A_DIM))
        screen.refresh()

        key = screen.getch()
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(options)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(options)
        elif key in (curses.KEY_ENTER, 10, 13):
            return options[selected]
        elif key in (ord("q"), 27):
            return None


def pause_screen(screen, lines):
    """Show a block of text and wait for any keypress."""
    screen.clear()
    for i, line in enumerate(lines):
        screen.addstr(i, 0, str(line)[:78], with_color(curses.A_NORMAL))
    screen.addstr(len(lines) + 1, 0, "[ press any key to continue ]", with_color(curses.A_DIM))
    screen.refresh()
    screen.getch()


def prompt_text(screen, prompt, default=""):
    """Read a single line of text from the user."""
    hint = f" [{default}]" if default else ""
    screen.addstr(0, 0, prompt + hint + " ", with_color(curses.A_NORMAL))
    screen.clrtoeol()
    screen.refresh()
    curses.echo()
    curses.curs_set(1)
    try:
        value = screen.getstr().decode().strip()
    finally:
        curses.noecho()
        curses.curs_set(0)
    return value or default


def to_int(value, default):
    """Parse an int, falling back to `default` on garbage input."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Menu handlers
# ---------------------------------------------------------------------------


def pick_switch(screen):
    """Ask the user to choose a switch; returns its dpid or None."""
    options = [f"{name} (dpid {dpid})" for name, dpid in SWITCHES]
    picked = arrow_menu(screen, "Which switch?", options)
    if picked is None:
        return None
    return SWITCHES[options.index(picked)][1]


def handle_list_flows(screen):
    dpid = pick_switch(screen)
    if dpid is None:
        return
    try:
        flows = get_flows(dpid)
    except Exception as exc:
        pause_screen(screen, ["Could not reach the controller:", str(exc)])
        return
    lines = [f"{len(flows)} flow(s) on switch s{dpid}:", ""]
    lines += [f"{i}: {describe_flow(flow)}" for i, flow in enumerate(flows)]
    pause_screen(screen, lines)


def handle_add_preset(screen):
    options = [f"{p['name']}  (s{p['dpid']}, prio {p['priority']})" for p in PRESETS]
    picked = arrow_menu(screen, "Add a preset rule", options)
    if picked is None:
        return
    preset = PRESETS[options.index(picked)]
    try:
        add_flow(preset["dpid"], preset["priority"], preset["match"], preset["actions"])
        pause_screen(screen, [
            "Installed:", f"  {preset['name']}",
            "", "Verify in the Mininet CLI:",
            f"  {preset['check']}",
        ])
    except Exception as exc:
        pause_screen(screen, ["Failed to install rule:", str(exc)])


def handle_delete_preset(screen):
    options = [f"{p['name']}  (s{p['dpid']}, prio {p['priority']})" for p in PRESETS]
    picked = arrow_menu(screen, "Delete a preset rule", options)
    if picked is None:
        return
    preset = PRESETS[options.index(picked)]
    try:
        delete_flow(preset["dpid"], preset["priority"], preset["match"])
        pause_screen(screen, [
            "Deleted:", f"  {preset['name']}",
            "", "Verify in the Mininet CLI:",
            f"  {preset['check'].replace('now FAILS', 'works again')}",
        ])
    except Exception as exc:
        pause_screen(screen, ["Failed to delete rule:", str(exc)])


def handle_delete_rule(screen):
    dpid = pick_switch(screen)
    if dpid is None:
        return
    try:
        flows = get_flows(dpid)
    except Exception as exc:
        pause_screen(screen, ["Could not reach the controller:", str(exc)])
        return

    # The table-miss rule (empty match, priority 0) keeps the network working.
    deletable = [f for f in flows if f.get("match") and f.get("priority", 0) > 0]
    if not deletable:
        pause_screen(screen, ["No deletable flows (only the table-miss rule exists)."])
        return

    labels = [f"{i}: {describe_flow(f)}" for i, f in enumerate(deletable)]
    picked = arrow_menu(screen, f"Which flow on s{dpid} to delete?", labels)
    if picked is None:
        return
    flow = deletable[labels.index(picked)]
    try:
        delete_flow(dpid, flow.get("priority"), flow.get("match"))
        pause_screen(screen, [f"Deleted: {describe_flow(flow)}"])
    except Exception as exc:
        pause_screen(screen, ["Failed to delete rule:", str(exc)])


def handle_custom_rule(screen):
    dpid = to_int(prompt_text(screen, "Switch dpid", "1"), 1)
    priority = to_int(prompt_text(screen, "Priority", "50"), 50)
    src = prompt_text(screen, "Source IP (blank = any)", "")
    dst = prompt_text(screen, "Dest IP (blank = any)", "")
    match = {"eth_type": ETH_TYPE_IP}
    if src:
        match["ipv4_src"] = src
    if dst:
        match["ipv4_dst"] = dst

    action = arrow_menu(screen, "Action?", ["DROP", "SET_QUEUE (queue_id + output port)"])
    if action is None:
        return

    if action.startswith("DROP"):
        actions, summary = [], "DROP"
    else:
        queue_id = to_int(prompt_text(screen, "Queue id", "1"), 1)
        port = to_int(prompt_text(screen, "Output port", "1"), 1)
        actions = [{"type": "SET_QUEUE", "queue_id": queue_id}, {"type": "OUTPUT", "port": port}]
        summary = f"set_queue {queue_id} -> output {port}"

    try:
        add_flow(dpid, priority, match, actions)
        pause_screen(screen, [
            "Installed rule:",
            f"  switch s{dpid} | prio {priority} | src={src or '*'} dst={dst or '*'} | {summary}",
        ])
    except Exception as exc:
        pause_screen(screen, ["Failed to install rule:", str(exc)])


def handle_cheat_sheet(screen):
    lines = ["Host -> IP", "-----------"]
    lines += [f"{name:<12} {ip}" for name, ip in HOSTS.items()]
    lines += ["", "Zones (firewall/QoS rules match these subnets):"]
    lines += [f"{zone:<12} {subnet}" for zone, subnet in SUBNETS.items()]
    lines += ["", "Quarantine Zone:"]
    lines += [f"{'Honeypot':<12} 10.0.99.10 (s1-eth7)"]
    pause_screen(screen, lines)


def handle_code_blue_menu(screen):
    options = [
        "1. Activate CODE BLUE (Unit: ICU_Room_1)",
        "2. Activate CODE BLUE (Custom Unit)",
        "3. Resolve Emergency (Restore Baseline)",
        "4. View Emergency Status",
    ]
    picked = arrow_menu(screen, "Code Blue - Dynamic QoS Preemption", options)
    if picked is None:
        return
    try:
        if "1. Activate" in picked:
            api_post("/hospital/emergency", {"status": "CODE_BLUE", "unit": "ICU_Room_1"})
            status = api_get("/hospital/emergency")
            pause_screen(screen, [
                "Emergency Activated!",
                f"State: {json.dumps(status.get('emergency_state'))}",
                "",
                "OpenFlow Preemption Rules Installed:",
                "  - ICU Telemetry -> Queue 3 (85 Mbps Ultra-Low Latency)",
                "  - Admin Department -> Queue 2 (Throttled to 1 Mbps)",
                "  - Guest WiFi -> Suspended / Dropped"
            ])
        elif "2. Activate" in picked:
            unit = prompt_text(screen, "Enter unit name:", "ICU_Room_2")
            api_post("/hospital/emergency", {"status": "CODE_BLUE", "unit": unit})
            status = api_get("/hospital/emergency")
            pause_screen(screen, ["Emergency Activated for " + unit, f"State: {json.dumps(status.get('emergency_state'))}"])
        elif "3. Resolve" in picked:
            api_post("/hospital/emergency", {"status": "RESOLVED"})
            pause_screen(screen, ["Emergency RESOLVED.", "Baseline QoS and departmental rules restored."])
        elif "4. View" in picked:
            status = api_get("/hospital/emergency")
            lines = ["Emergency Status:"] + json.dumps(status, indent=2).split("\n")
            pause_screen(screen, lines)
    except Exception as exc:
        pause_screen(screen, ["Error contacting controller:", str(exc)])


def handle_quarantine_menu(screen):
    options = [
        "1. View Quarantined IoMT Devices",
        "2. Manually Quarantine IoMT Host (e.g. h_mri1)",
        "3. Release IoMT Host from Quarantine",
    ]
    picked = arrow_menu(screen, "IoMT Anomaly Quarantine", options)
    if picked is None:
        return
    try:
        if "1. View" in picked:
            data = api_get("/hospital/quarantine")
            lines = ["IoMT Quarantine Registry:"] + json.dumps(data, indent=2).split("\n")
            pause_screen(screen, lines)
        elif "2. Manually" in picked:
            ip = prompt_text(screen, "Enter host IP to quarantine:", "10.0.4.11")
            api_post("/hospital/quarantine", {"host": ip, "action": "ISOLATE"})
            pause_screen(screen, [f"Host {ip} Quarantined!", "Priority 90 drop rules installed on switches s5 and s1."])
        elif "3. Release" in picked:
            ip = prompt_text(screen, "Enter host IP to release:", "10.0.4.11")
            api_post("/hospital/quarantine", {"host": ip, "action": "RELEASE"})
            pause_screen(screen, [f"Host {ip} Released from Quarantine.", "Normal communication restored."])
    except Exception as exc:
        pause_screen(screen, ["Error contacting controller:", str(exc)])


def handle_failover_menu(screen):
    try:
        data = api_get("/hospital/failover")
        lines = [
            "Sub-Millisecond Telemetry Resilience (Fast Failover):",
            "",
            "Controller Configuration:",
        ] + json.dumps(data, indent=2).split("\n") + [
            "",
            "Datapath Implementation:",
            "  Switch s2 (Datacenter) & Switch s1 (Core) use OpenFlow 1.3 OFPGT_FF.",
            "  - Bucket 1 monitors primary aggregation link (port 1).",
            "  - Bucket 2 monitors redundant backup link.",
            "  If primary link drops, OVS switches in hardware (< 10 ms)."
        ]
        pause_screen(screen, lines)
    except Exception as exc:
        pause_screen(screen, ["Error contacting controller:", str(exc)])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

MAIN_MENU = [
    ("List flows on a switch", handle_list_flows),
    ("Code Blue: Trigger / Resolve Emergency", handle_code_blue_menu),
    ("IoMT Security: Quarantine & Anomaly Defense", handle_quarantine_menu),
    ("Resilience: Fast Failover Groups Inspection", handle_failover_menu),
    ("Add a preset rule", handle_add_preset),
    ("Add a custom rule", handle_custom_rule),
    ("Delete a rule (pick from live flows)", handle_delete_rule),
    ("Delete a preset rule", handle_delete_preset),
    ("Show host cheat-sheet", handle_cheat_sheet),
    ("Exit", None),
]


def run(screen):
    screen.keypad(True)
    init_colors()
    while True:
        labels = [item[0] for item in MAIN_MENU]
        picked = arrow_menu(screen, "FLOW CONSOLE - Hospital SDN", labels)
        if picked is None:
            break
        handler = MAIN_MENU[labels.index(picked)][1]
        if handler is None:
            break
        handler(screen)


def main():
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    except curses.error as exc:
        print(f"Interactive terminal required: {exc}")
        print("Run this inside a normal terminal (not a pipe/file).")


if __name__ == "__main__":
    main()

