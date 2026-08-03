from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import ipv4

class HospitalController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(HospitalController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install table-miss flow entry
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        # Proactive Firewall Rules
        self.install_firewall_rules(datapath)

        # Proactive QoS Rules (Only on Datacenter Switch - DPID 2)
        if datapath.id == 2:
            self.install_qos_rules(datapath)

    def install_qos_rules(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Subnets
        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')

        # Port 1 on s2 connects to s_core
        OUT_PORT = 1
        QOS_PRIORITY = 20

        # IoT Traffic -> Queue 2 (Throttled)
        match_iot = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_IOT)
        actions_iot = [parser.OFPActionSetQueue(2), parser.OFPActionOutput(OUT_PORT)]
        self.add_flow(datapath, QOS_PRIORITY, match_iot, actions_iot)

        # Medical Traffic -> Queue 1 (High Priority)
        match_med = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=SUBNET_MED)
        actions_med = [parser.OFPActionSetQueue(1), parser.OFPActionOutput(OUT_PORT)]
        self.add_flow(datapath, QOS_PRIORITY, match_med, actions_med)

        self.logger.info("QoS rules installed on switch %s", datapath.id)

    def install_firewall_rules(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Subnets
        SUBNET_DC = ('10.0.1.0', '255.255.255.0')
        SUBNET_MED = ('10.0.2.0', '255.255.255.0')
        SUBNET_ADMIN = ('10.0.3.0', '255.255.255.0')
        SUBNET_IOT = ('10.0.4.0', '255.255.255.0')
        SUBNET_GUEST = ('10.0.5.0', '255.255.255.0')
        
        MED_SRV_IP = '10.0.1.10'
        ADMIN_SRV_IP = '10.0.1.20'

        # Priority for firewall drops (must be higher than L2 learning priority 1)
        FW_PRIORITY = 10

        # Helper to add drop rule
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
            
            actions = [] # Empty actions means DROP
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


    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        
        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})

        # self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
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
