#!/usr/bin/env python3
"""
Hospital SDN OpenFlow 1.3 Controller

Incorporates:
1. "Code Blue" Event-Driven Dynamic QoS Preemption Engine:
   - WSGI REST endpoint POST /hospital/emergency {"status": "CODE_BLUE"|"RESOLVED", "unit": ...}
   - Dynamic priority 100 preemption flows: prioritizes ICU telemetry, throttles Admin, suspends Guest.
2. Automated IoMT Anomaly Quarantine (Reactive Security):
   - Periodic flow/port stats sampling loop (ryu.lib.hub).
   - Autonomous isolation of infected devices exceeding bandwidth threshold (> 1 Mbps).
   - Priority 90 quarantine flows, alerting, and REST endpoint for remediation.
3. Sub-Millisecond Telemetry Resilience with Fast Failover Groups (OFPGT_FF):
   - OpenFlow 1.3 Fast Failover Group Tables on Datacenter (s2) and Core (s1) switches.
   - Dual buckets monitoring primary and backup links for instantaneous hardware-level failover.
4. Baseline Departmental Firewall and QoS Enforcement:
   - Proactive isolation of Guest WiFi, departmental boundaries, and baseline OVS queue steering.
"""

import time
import json
from webob import Response

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4
from ryu.lib import hub
from ryu.app.wsgi import ControllerBase, WSGIApplication, route


HOSPITAL_APP_NAME = 'hospital_controller_app'


class HospitalRestController(ControllerBase):
    """
    REST API controller exposed via Ryu WSGI on port 8080.
    Provides RESTful control and telemetry endpoints for Examiners and Admins.
    """
    def __init__(self, req, link, data, **config):
        super(HospitalRestController, self).__init__(req, link, data, **config)
        self.hospital_app = data[HOSPITAL_APP_NAME]

    def _json_response(self, data, status=200):
        return Response(status=status, content_type='application/json', charset='UTF-8',
                        body=json.dumps(data, indent=2).encode('utf-8'))

    @route('hospital', '/hospital/emergency', methods=['POST'])
    def set_emergency(self, req, **kwargs):
        try:
            body = json.loads(req.body.decode('utf-8')) if req.body else {}
        except Exception as e:
            return self._json_response({"error": f"Invalid JSON body: {str(e)}"}, status=400)
        status = body.get('status', '').upper()
        unit = body.get('unit', 'ICU_Room_1')
        res = self.hospital_app.handle_emergency_event(status, unit)
        return self._json_response(res)

    @route('hospital', '/hospital/emergency', methods=['GET'])
    def get_emergency(self, req, **kwargs):
        res = self.hospital_app.get_emergency_status()
        return self._json_response(res)

    @route('hospital', '/hospital/quarantine', methods=['GET'])
    def get_quarantine(self, req, **kwargs):
        res = self.hospital_app.get_quarantine_status()
        return self._json_response(res)

    @route('hospital', '/hospital/quarantine', methods=['POST'])
    def manage_quarantine(self, req, **kwargs):
        try:
            body = json.loads(req.body.decode('utf-8')) if req.body else {}
        except Exception as e:
            return self._json_response({"error": f"Invalid JSON body: {str(e)}"}, status=400)
        host = body.get('host') or body.get('ip', '')
        action = body.get('action', '').upper()
        res = self.hospital_app.handle_quarantine_action(host, action)
        return self._json_response(res)

    @route('hospital', '/hospital/failover', methods=['GET'])
    def get_failover(self, req, **kwargs):
        res = self.hospital_app.get_failover_status()
        return self._json_response(res)


class HospitalController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {
        'wsgi': WSGIApplication
    }

    def __init__(self, *args, **kwargs):
        super(HospitalController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}

        # Idea 1: Code Blue state tracking
        self.emergency_state = {
            'status': 'NORMAL',
            'unit': None,
            'timestamp': time.time(),
            'preemption_active': False
        }

        # Idea 2: IoMT Anomaly Quarantine tracking
        self.quarantine_registry = {}  # ip -> {'timestamp', 'rate_mbps', 'status'}
        self.flow_stats_cache = {}    # (dpid, ip) -> (byte_count, packet_count, timestamp)
        self.iomt_anomaly_threshold_mbps = 1.0  # Baseline IoMT limit = 1.0 Mbps

        # Idea 3: Fast Failover status
        self.failover_configured = {
            's1': {'primary_port': 1, 'backup_port': 6, 'group_id': 1},
            's2': {'primary_port': 1, 'backup_port': 2, 'group_id': 1}
        }
        self.failover_active = {1: False, 2: False}

        # Register WSGI REST endpoint
        wsgi = kwargs.get('wsgi')
        if wsgi:
            wsgi.register(HospitalRestController, {HOSPITAL_APP_NAME: self})
            self.logger.info("[REST API] Hospital SDN Endpoints registered on Ryu WSGI (port 8080)")

        # Start periodic stats monitoring thread for IoMT Anomaly Detection (Idea 2)
        self.monitor_thread = hub.spawn(self._monitor_loop)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[datapath.id] = datapath
            self.logger.info("Switch connected: DPID %s", datapath.id)
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                self.logger.info("Switch disconnected: DPID %s", datapath.id)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath

        # 1. Table-miss flow entry (send to controller)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        # 2. Idea 3: Fast Failover Groups on s1 (Core) and s2 (Datacenter)
        if datapath.id in (1, 2):
            self.install_fast_failover_group(datapath)

        # 3. Proactive Firewall Rules on all switches
        self.install_firewall_rules(datapath)

        # 4. Proactive Baseline QoS Rules
        if datapath.id == 2:
            self.install_dc_qos_and_forwarding(datapath)
        elif datapath.id == 1:
            self.install_core_forwarding_rules(datapath)

    # =========================================================================
    # Idea 3: Fast Failover Groups (OFPGT_FF)
    # =========================================================================
    def install_fast_failover_group(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        if dpid == 2:
            # Switch 2 (Datacenter): Port 1 connects to s1 (Primary), Port 2 connects to s1 (Backup)
            primary_port = 1
            backup_port = 2
        elif dpid == 1:
            # Switch 1 (Core): Port 1 connects to s2 (Primary), Port 6 connects to s2 (Backup)
            primary_port = 1
            backup_port = 6
        else:
            return

        buckets = [
            parser.OFPBucket(
                weight=0,
                watch_port=primary_port,
                watch_group=ofproto.OFPG_ANY,
                actions=[parser.OFPActionOutput(primary_port)]
            ),
            parser.OFPBucket(
                weight=0,
                watch_port=backup_port,
                watch_group=ofproto.OFPG_ANY,
                actions=[parser.OFPActionOutput(backup_port)]
            )
        ]

        # In OpenFlow 1.3, remove group if exists then add
        del_mod = parser.OFPGroupMod(datapath, command=ofproto.OFPGC_DELETE,
                                     type_=ofproto.OFPGT_FF, group_id=1)
        datapath.send_msg(del_mod)

        add_mod = parser.OFPGroupMod(
            datapath,
            command=ofproto.OFPGC_ADD,
            type_=ofproto.OFPGT_FF,
            group_id=1,
            buckets=buckets
        )
        datapath.send_msg(add_mod)
        self.logger.info("[FAILOVER] Installed Fast Failover Group 1 on DPID %s: Bucket1(watch_port=%s) -> Bucket2(watch_port=%s)",
                         dpid, primary_port, backup_port)

    def install_dc_qos_and_forwarding(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')
        SUBNET_ADMIN = ('10.0.3.0', '255.255.255.0')
        SUBNET_GUEST = ('10.0.5.0', '255.255.255.0')

        QOS_PRIORITY = 20

        # Outbound from Datacenter: uses Group 1 (Fast Failover) with OVS QoS queueing
        # IoT Traffic -> Queue 2 (Throttled to 1Mbps)
        match_iot = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_IOT)
        actions_iot = [parser.OFPActionSetQueue(2), parser.OFPActionGroup(1)]
        self.add_flow(datapath, QOS_PRIORITY, match_iot, actions_iot)

        # Medical Traffic -> Queue 1 (High Priority 50Mbps)
        match_med = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_MED)
        actions_med = [parser.OFPActionSetQueue(1), parser.OFPActionGroup(1)]
        self.add_flow(datapath, QOS_PRIORITY, match_med, actions_med)

        # Admin Traffic -> Queue 0 (Default)
        match_admin = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_ADMIN)
        actions_admin = [parser.OFPActionSetQueue(0), parser.OFPActionGroup(1)]
        self.add_flow(datapath, QOS_PRIORITY, match_admin, actions_admin)

        # Local Server Delivery on s2
        # Port 3 = h_med_srv (10.0.1.10)
        match_med_srv = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst='10.0.1.10')
        actions_med_srv = [parser.OFPActionOutput(3)]
        self.add_flow(datapath, QOS_PRIORITY, match_med_srv, actions_med_srv)

        # Port 4 = h_adm_srv (10.0.1.20)
        match_adm_srv = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst='10.0.1.20')
        actions_adm_srv = [parser.OFPActionOutput(4)]
        self.add_flow(datapath, QOS_PRIORITY, match_adm_srv, actions_adm_srv)

        self.logger.info("Baseline QoS and Fast Failover flows installed on Datacenter switch %s", datapath.id)

    def install_core_forwarding_rules(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        SUBNET_DC = ('10.0.1.0', '255.255.255.0')
        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_ADMIN = ('10.0.3.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')
        HONEYPOT_IP = '10.0.99.10'

        # Baseline: Datacenter-bound traffic from core uses Fast Failover Group 1 with appropriate queues:
        # Medical -> Queue 1 (50Mbps min)
        match_med = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_MED, ipv4_dst=SUBNET_DC)
        self.add_flow(datapath, 20, match_med, [parser.OFPActionSetQueue(1), parser.OFPActionGroup(1)])

        # Admin -> Queue 0 (Default)
        match_admin = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_ADMIN, ipv4_dst=SUBNET_DC)
        self.add_flow(datapath, 20, match_admin, [parser.OFPActionSetQueue(0), parser.OFPActionGroup(1)])

        # IoT -> Queue 2 (1Mbps)
        match_iot = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_IOT, ipv4_dst=SUBNET_DC)
        self.add_flow(datapath, 20, match_iot, [parser.OFPActionSetQueue(2), parser.OFPActionGroup(1)])

        # Fallback Datacenter-bound traffic from core uses Fast Failover Group 1
        match_dc = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_DC)
        actions_dc = [parser.OFPActionGroup(1)]
        self.add_flow(datapath, 19, match_dc, actions_dc)

        # Quarantine / Honeypot host is on Core port 7
        match_honeypot = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=HONEYPOT_IP)
        actions_honeypot = [parser.OFPActionOutput(7)]
        self.add_flow(datapath, 20, match_honeypot, actions_honeypot)

        self.logger.info("Fast Failover and QoS forwarding rules installed on Core switch %s", datapath.id)

    def install_firewall_rules(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        SUBNET_DC = ('10.0.1.0', '255.255.255.0')
        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_ADMIN = ('10.0.3.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')
        SUBNET_GUEST = ('10.0.5.0', '255.255.255.0')
        
        MED_SRV_IP = '10.0.1.10'
        ADMIN_SRV_IP = '10.0.1.20'

        FW_PRIORITY = 10

        def add_drop_rule(src_ip_mask, dst_ip_mask=None, dst_ip=None):
            if dst_ip_mask:
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                        ipv4_src=src_ip_mask,
                                        ipv4_dst=dst_ip_mask)
            elif dst_ip:
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                        ipv4_src=src_ip_mask,
                                        ipv4_dst=dst_ip)
            else:
                return
            actions = []  # Empty actions = DROP
            self.add_flow(datapath, FW_PRIORITY, match, actions)

        # 1. Guest Isolation: Drop traffic from Guest to any internal subnet
        add_drop_rule(SUBNET_GUEST, dst_ip_mask=SUBNET_DC)
        add_drop_rule(SUBNET_GUEST, dst_ip_mask=SUBNET_MED)
        add_drop_rule(SUBNET_GUEST, dst_ip_mask=SUBNET_ADMIN)
        add_drop_rule(SUBNET_GUEST, dst_ip_mask=SUBNET_IOT)

        # 2. IoT Isolation: Drop IoT traffic to Admin, Guest, Medical
        add_drop_rule(SUBNET_IOT, dst_ip_mask=SUBNET_ADMIN)
        add_drop_rule(SUBNET_IOT, dst_ip_mask=SUBNET_GUEST)
        add_drop_rule(SUBNET_IOT, dst_ip_mask=SUBNET_MED)
        # IoT can only access Med Server, drop access to Admin Server
        add_drop_rule(SUBNET_IOT, dst_ip=ADMIN_SRV_IP)

        # 3. Department access constraints
        # Medical cannot access Admin Server
        add_drop_rule(SUBNET_MED, dst_ip=ADMIN_SRV_IP)
        # Admin cannot access Med Server
        add_drop_rule(SUBNET_ADMIN, dst_ip=MED_SRV_IP)

        self.logger.info("Firewall rules installed on switch %s", datapath.id)

    # =========================================================================
    # Idea 1: "Code Blue" Event-Driven Dynamic QoS Preemption Engine
    # =========================================================================
    def handle_emergency_event(self, status, unit='ICU_Room_1'):
        status = status.upper()
        if status == 'CODE_BLUE':
            self.emergency_state = {
                'status': 'CODE_BLUE',
                'unit': unit,
                'timestamp': time.time(),
                'preemption_active': True
            }
            self.logger.warning("=================================================================")
            self.logger.warning("[CODE BLUE ALERT] Unit '%s' initiated emergency state!", unit)
            self.logger.warning("Dynamic QoS Preemption engaged:")
            self.logger.warning("  -> ICU Telemetry: Preempted to Queue 3 (85 Mbps Ultra-Low-Latency)")
            self.logger.warning("  -> Admin Traffic: Throttled to Queue 2 (1 Mbps minimum)")
            self.logger.warning("  -> Guest Traffic: Suspended (DROP actions=[])")
            self.logger.warning("=================================================================")

            self._install_code_blue_rules(unit)
            return {
                "status": "SUCCESS",
                "message": f"CODE_BLUE activated for {unit}",
                "emergency_state": self.emergency_state
            }

        elif status == 'RESOLVED':
            prev_unit = self.emergency_state.get('unit', 'ICU')
            self.emergency_state = {
                'status': 'NORMAL',
                'unit': None,
                'timestamp': time.time(),
                'preemption_active': False
            }
            self.logger.info("=================================================================")
            self.logger.info("[CODE BLUE RESOLVED] Emergency cleared for '%s'.", prev_unit)
            self.logger.info("Restoring baseline QoS and flow rules across hospital network.")
            self.logger.info("=================================================================")

            self._remove_code_blue_rules()
            return {
                "status": "SUCCESS",
                "message": f"Emergency resolved for {prev_unit}. Baseline QoS restored.",
                "emergency_state": self.emergency_state
            }
        else:
            return {"status": "ERROR", "message": f"Unknown emergency status: {status}"}

    def _install_code_blue_rules(self, unit):
        CODE_BLUE_PRIORITY = 100
        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_ADMIN = ('10.0.3.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')
        SUBNET_GUEST = ('10.0.5.0', '255.255.255.0')
        SUBNET_DC = ('10.0.1.0', '255.255.255.0')

        # 1. On Datacenter Switch (s2, DPID 2)
        dp2 = self.datapaths.get(2)
        if dp2:
            parser = dp2.ofproto_parser
            # Prioritize ICU / Medical telemetry to Queue 3 (85Mbps guarantee) via Group 1
            match_med = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_MED)
            actions_med = [parser.OFPActionSetQueue(3), parser.OFPActionGroup(1)]
            self.add_flow(dp2, CODE_BLUE_PRIORITY, match_med, actions_med)

            # Prioritize IoT telemetry to Queue 3 (85Mbps guarantee) via Group 1
            match_iot = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_IOT)
            actions_iot = [parser.OFPActionSetQueue(3), parser.OFPActionGroup(1)]
            self.add_flow(dp2, CODE_BLUE_PRIORITY, match_iot, actions_iot)

            # Throttle Admin traffic down to Queue 2 (1Mbps)
            match_admin = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_ADMIN)
            actions_admin = [parser.OFPActionSetQueue(2), parser.OFPActionGroup(1)]
            self.add_flow(dp2, CODE_BLUE_PRIORITY, match_admin, actions_admin)

            # Drop Guest traffic
            match_guest = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_GUEST)
            self.add_flow(dp2, CODE_BLUE_PRIORITY, match_guest, [])

        # 2. On Core Switch (s1, DPID 1)
        dp1 = self.datapaths.get(1)
        if dp1:
            parser = dp1.ofproto_parser
            # Ingress Guest traffic dropped
            match_guest_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_GUEST)
            self.add_flow(dp1, CODE_BLUE_PRIORITY, match_guest_in, [])

            # Ingress ICU/Med traffic prioritized to Queue 3 (85Mbps)
            match_med_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_MED, ipv4_dst=SUBNET_DC)
            actions_med_in = [parser.OFPActionSetQueue(3), parser.OFPActionGroup(1)]
            self.add_flow(dp1, CODE_BLUE_PRIORITY, match_med_in, actions_med_in)

            # Ingress IoT/Telemetry traffic prioritized to Queue 3 (85Mbps)
            match_iot_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_IOT, ipv4_dst=SUBNET_DC)
            actions_iot_in = [parser.OFPActionSetQueue(3), parser.OFPActionGroup(1)]
            self.add_flow(dp1, CODE_BLUE_PRIORITY, match_iot_in, actions_iot_in)

            # Ingress Admin traffic throttled to Queue 2 (1Mbps)
            match_admin_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_ADMIN, ipv4_dst=SUBNET_DC)
            actions_admin_in = [parser.OFPActionSetQueue(2), parser.OFPActionGroup(1)]
            self.add_flow(dp1, CODE_BLUE_PRIORITY, match_admin_in, actions_admin_in)

    def _remove_code_blue_rules(self):
        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_ADMIN = ('10.0.3.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')
        SUBNET_GUEST = ('10.0.5.0', '255.255.255.0')
        SUBNET_DC = ('10.0.1.0', '255.255.255.0')

        dp2 = self.datapaths.get(2)
        if dp2:
            parser = dp2.ofproto_parser
            for subnet in (SUBNET_MED, SUBNET_ADMIN, SUBNET_IOT, SUBNET_GUEST):
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=subnet)
                self.remove_flows(dp2, priority=100, match=match, strict=True)
            self.install_dc_qos_and_forwarding(dp2)

        dp1 = self.datapaths.get(1)
        if dp1:
            parser = dp1.ofproto_parser
            match_guest_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=SUBNET_GUEST)
            self.remove_flows(dp1, priority=100, match=match_guest_in, strict=True)
            for subnet in (SUBNET_ADMIN, SUBNET_MED, SUBNET_IOT):
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=subnet, ipv4_dst=SUBNET_DC)
                self.remove_flows(dp1, priority=100, match=match, strict=True)
            self.install_core_forwarding_rules(dp1)

    def get_emergency_status(self):
        return {
            "emergency_state": self.emergency_state,
            "connected_switches": list(self.datapaths.keys()),
            "preemption_rules_installed": self.emergency_state['preemption_active']
        }

    # =========================================================================
    # Idea 2: Automated IoMT Anomaly Quarantine (Closed-Loop Reactive Security)
    # =========================================================================
    def _monitor_loop(self):
        while True:
            hub.sleep(2)  # Sample every 2 seconds
            for dp in list(self.datapaths.values()):
                if dp.id in (1, 2, 5):
                    self._request_flow_stats(dp)

    def _request_flow_stats(self, datapath):
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        now = time.time()

        for stat in body:
            ipv4_src = stat.match.get('ipv4_src')
            if not ipv4_src or not isinstance(ipv4_src, str):
                continue

            # Target IoMT hosts on subnet 10.0.4.X
            if ipv4_src.startswith('10.0.4.'):
                recent_release = self.quarantine_registry.get(ipv4_src, {}).get('released_at', 0)
                if now - recent_release < 10.0:
                    continue

                flow_key = (dpid, ipv4_src)
                prev = self.flow_stats_cache.get(flow_key)
                self.flow_stats_cache[flow_key] = (stat.byte_count, stat.packet_count, now)

                if prev:
                    prev_bytes, prev_pkts, prev_time = prev
                    delta_t = now - prev_time
                    if delta_t >= 1.0:
                        rate_bps = max(0, (stat.byte_count - prev_bytes) * 8.0 / delta_t)
                        rate_mbps = rate_bps / 1_000_000.0

                        # Check if IoMT device exceeds baseline threshold
                        if rate_mbps > self.iomt_anomaly_threshold_mbps:
                            if ipv4_src not in self.quarantine_registry or \
                               self.quarantine_registry[ipv4_src]['status'] != 'QUARANTINED':
                                self.quarantine_host(ipv4_src, rate_mbps)

    def quarantine_host(self, host_ip, rate_mbps):
        QUARANTINE_PRIORITY = 90
        HONEYPOT_IP = '10.0.99.10'

        self.quarantine_registry[host_ip] = {
            'timestamp': time.time(),
            'rate_mbps': round(rate_mbps, 3),
            'status': 'QUARANTINED',
            'action': 'ISOLATED_AND_REDIRECTED'
        }

        self.logger.warning("*****************************************************************")
        self.logger.warning("[SECURITY ALERT] IoMT Host %s anomalous traffic detected!", host_ip)
        self.logger.warning("Observed Bandwidth: %.2f Mbps (Baseline Threshold: %.2f Mbps)",
                            rate_mbps, self.iomt_anomaly_threshold_mbps)
        self.logger.warning("Autonomous Action: Installing OpenFlow quarantine rule (priority=%s)!", QUARANTINE_PRIORITY)
        self.logger.warning("Traffic from %s is immediately quarantined and blocked.", host_ip)
        self.logger.warning("*****************************************************************")

        # Install quarantine flow rules on IoT switch (s5), Core (s1), and Datacenter (s2)
        for dpid in (5, 1, 2):
            dp = self.datapaths.get(dpid)
            if dp:
                parser = dp.ofproto_parser
                # Rule 1: Drop all outbound communications to prevent lateral infection
                match_out = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=host_ip)
                self.add_flow(dp, QUARANTINE_PRIORITY, match_out, [])
                # Rule 2: Drop all inbound communications to completely isolate host
                match_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=host_ip)
                self.add_flow(dp, QUARANTINE_PRIORITY, match_in, [])

    def handle_quarantine_action(self, host_ip, action):
        action = action.upper()
        if action == 'RELEASE':
            # Remove quarantine flows (priority 90) specifically matching ipv4_src or ipv4_dst
            for dpid in (5, 1, 2):
                dp = self.datapaths.get(dpid)
                if dp:
                    parser = dp.ofproto_parser
                    match_out = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=host_ip)
                    self.remove_flows(dp, priority=90, match=match_out, strict=True)
                    match_in = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=host_ip)
                    self.remove_flows(dp, priority=90, match=match_in, strict=True)

            # Clear cache for this host to avoid instant re-trigger
            for k in list(self.flow_stats_cache.keys()):
                if k[1] == host_ip:
                    del self.flow_stats_cache[k]

            if host_ip in self.quarantine_registry:
                self.quarantine_registry[host_ip]['status'] = 'RELEASED'
                self.quarantine_registry[host_ip]['released_at'] = time.time()

            self.logger.info("[SECURITY] IoMT Host %s released from quarantine by administrator.", host_ip)
            return {
                "status": "SUCCESS",
                "message": f"Host {host_ip} released from quarantine.",
                "quarantine_state": self.quarantine_registry.get(host_ip)
            }
        elif action == 'ISOLATE':
            self.quarantine_host(host_ip, 0.0)
            return {
                "status": "SUCCESS",
                "message": f"Host {host_ip} manually quarantined by administrator."
            }
        else:
            return {"status": "ERROR", "message": f"Unknown quarantine action: {action}"}

    def get_quarantine_status(self):
        return {
            "threshold_mbps": self.iomt_anomaly_threshold_mbps,
            "quarantined_hosts": self.quarantine_registry
        }

    def get_failover_status(self):
        return {
            "group_table_type": "OFPGT_FF (Fast Failover)",
            "failover_configured": self.failover_configured,
            "switches_online": [dpid for dpid in self.datapaths]
        }

    # =========================================================================
    # OpenFlow Flow Management Helpers
    # =========================================================================
    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    def remove_flows(self, datapath, priority, match=None, strict=False):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        if match is None:
            match = parser.OFPMatch()
        cmd = ofproto.OFPFC_DELETE_STRICT if strict else ofproto.OFPFC_DELETE
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=cmd,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            priority=priority,
            match=match
        )
        datapath.send_msg(mod)

    # =========================================================================
    # L2 Learning Switch Logic with Standby Loop-Prevention & Fast Failover
    # =========================================================================
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto

        is_down = (msg.desc.state & ofproto.OFPPS_LINK_DOWN) or (reason == ofproto.OFPPR_DELETE)
        if dpid == 2 and port_no == 1:
            self.failover_active[2] = bool(is_down)
            if is_down:
                self.logger.warning("[FAILOVER] Switch s2 (Datacenter) primary port 1 is DOWN! Standby link port 2 engaged.")
            else:
                self.logger.info("[FAILOVER] Switch s2 (Datacenter) primary port 1 is UP! Primary link active.")
        elif dpid == 1 and port_no == 1:
            self.failover_active[1] = bool(is_down)
            if is_down:
                self.logger.warning("[FAILOVER] Switch s1 (Core) primary port 1 is DOWN! Standby link port 6 engaged.")
            else:
                self.logger.info("[FAILOVER] Switch s1 (Core) primary port 1 is UP! Primary link active.")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        # Loop-prevention for redundant parallel links:
        # s1: port 1 primary, port 6 standby
        # s2: port 1 primary, port 2 standby
        # Drop packets entering on the standby port when the primary link is healthy
        if dpid == 1 and in_port == 6 and not self.failover_active.get(1, False):
            return
        if dpid == 2 and in_port == 2 and not self.failover_active.get(2, False):
            return

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            target_port = self.mac_to_port[dpid][dst]
            # Route through Fast Failover Group 1 for inter-switch trunk links
            if dpid == 2 and target_port in (1, 2):
                actions = [parser.OFPActionGroup(1)]
            elif dpid == 1 and target_port in (1, 6):
                actions = [parser.OFPActionGroup(1)]
            else:
                actions = [parser.OFPActionOutput(target_port)]
            out_port = target_port
        else:
            # Broadcast / Flood: flood strictly to active ports, omitting the inactive standby link
            if dpid == 1:
                # Core switch ports: 1 (s2), 2 (s3), 3 (s4), 4 (s5), 5 (s6), 7 (h_quar). Standby: 6
                active_trunk = 6 if self.failover_active.get(1, False) else 1
                flood_ports = [active_trunk, 2, 3, 4, 5, 7]
                actions = [parser.OFPActionOutput(p) for p in flood_ports if p != in_port]
            elif dpid == 2:
                # DC switch ports: 1 (s1), 3 (h_med_srv), 4 (h_adm_srv). Standby: 2
                active_trunk = 2 if self.failover_active.get(2, False) else 1
                flood_ports = [active_trunk, 3, 4]
                actions = [parser.OFPActionOutput(p) for p in flood_ports if p != in_port]
            else:
                actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
            out_port = ofproto.OFPP_FLOOD

        if out_port != ofproto.OFPP_FLOOD:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if ip_pkt:
                match = parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
                                         ipv4_src=ip_pkt.src, ipv4_dst=ip_pkt.dst)
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

