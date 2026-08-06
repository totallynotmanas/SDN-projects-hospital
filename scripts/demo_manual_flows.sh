#!/bin/bash
#
# Demo: Manual Flow Rule Insertion via the Ryu REST API
#
# Prerequisites:
#   1. The controller must be running WITH ryu.app.ofctl_rest loaded
#      (start_network.sh does this automatically). REST API = port 8080.
#   2. The Mininet topology must be up (you should be sitting in the
#      `mininet>` CLI in another terminal).
#
# Run this in a THIRD terminal while the network is up:
#     bash scripts/demo_manual_flows.sh
#
# The script pauses after each rule so you can verify the effect in the
# Mininet CLI (e.g. `h_doc1 ping -c 3 h_med_srv`).

set -e

API="http://127.0.0.1:8080"
CORE_DPID=1        # s1 (core switch) - sits on the path between hosts
DROP_PRIORITY=50   # must be higher than firewall (10), QoS (20), L2 (1)

echo "=============================================================="
echo "  DEMO: MANUAL FLOW RULE INSERTION VIA CONTROLLER API"
echo "=============================================================="

echo
echo "== 1. Show flows ALREADY installed by the controller =="
echo "    (firewall + QoS rules were pushed proactively at startup)"
curl -s "$API/stats/flow/$CORE_DPID" | python3 -m json.tool | grep -E '"priority"|"ipv4_' | head -30

echo
echo "== 2. Prove h_doc1 can currently reach h_med_srv =="
echo "    In the Mininet CLI run:  h_doc1 ping -c 3 h_med_srv   (should SUCCEED)"
read -r -p "    Press Enter once you have confirmed the ping succeeds... "

echo
echo "== 3. MANUALLY INSERT a DROP rule (block h_doc1 -> h_med_srv) =="
curl -s -X POST -d "{
  \"dpid\": $CORE_DPID,
  \"priority\": $DROP_PRIORITY,
  \"match\": {
    \"eth_type\": 2048,
    \"ipv4_src\": \"10.0.2.11\",
    \"ipv4_dst\": \"10.0.1.10\"
  },
  \"actions\": []
}" "$API/stats/flowentry/add"
echo "    -> REST response above should be empty (HTTP 200)."

echo
echo "== 4. Verify the rule was installed (ovs-ofctl) =="
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep "priority=$DROP_PRIORITY"

echo
echo "== 5. Prove the rule works =="
echo "    In the Mininet CLI run:  h_doc1 ping -c 3 h_med_srv   (should now FAIL)"
read -r -p "    Press Enter once you have confirmed the ping fails... "

echo
echo "== 6. MANUALLY DELETE the rule we just added =="
curl -s -X POST -d "{
  \"dpid\": $CORE_DPID,
  \"priority\": $DROP_PRIORITY,
  \"match\": {
    \"eth_type\": 2048,
    \"ipv4_src\": \"10.0.2.11\",
    \"ipv4_dst\": \"10.0.1.10\"
  }
}" "$API/stats/flowentry/delete"
echo "    -> REST response above should be empty (HTTP 200)."

echo
echo "== 7. Confirm rule is gone =="
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep "priority=$DROP_PRIORITY" \
    && echo "    WARNING: rule still present!" || echo "    Rule removed OK."

echo
echo "== 8. (Optional) MANUALLY INSERT a QoS flow via the API =="
echo "    Set Queue 1 for Admin-subnet traffic on switch 2 (s2, datacenter)."
curl -s -X POST -d '{
  "dpid": 2,
  "priority": 20,
  "match": {
    "eth_type": 2048,
    "ipv4_dst": "10.0.3.0/24"
  },
  "actions": [
    {"type": "SET_QUEUE", "queue_id": 1},
    {"type": "OUTPUT", "port": 1}
  ]
}' "$API/stats/flowentry/add"
echo
sudo ovs-ofctl -O OpenFlow13 dump-flows s2 | grep "set_queue:1"

echo
echo "Demo complete. Delete the QoS flow if you added it:"
echo "  curl -s -X POST -d '{\"dpid\": 2, \"priority\": 20,"
echo "    \"match\": {\"eth_type\": 2048, \"ipv4_dst\": \"10.0.3.0/24\"}}' \\"
echo "    $API/stats/flowentry/delete"
