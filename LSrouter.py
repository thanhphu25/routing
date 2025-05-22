####################################################
# LSrouter_fixed.py
# Fixed Link State routing protocol implementation
####################################################

from packet import Packet
from router import Router
import json
import networkx as nx

class LSrouter(Router):
    """Link state routing protocol implementation (fixed)."""

    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)  # Initialize base class
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        # Maps router to its link state (neighbors and costs)
        self.link_state = {self.addr: {}}
        # Maps router to its latest sequence number
        self.sequence_numbers = {self.addr: 0}
        # Undirected network graph for shortest path computation
        self.graph = nx.Graph()
        # Maps destination to (port, cost)
        self.forwarding_table = {}

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        if packet.kind == Packet.ROUTING:
            received = json.loads(packet.content)
            src = received["src"]
            seq_num = received["seq_num"]
            neighbors = received["neighbors"]
            # Newer sequence number => update LS database
            if seq_num > self.sequence_numbers.get(src, -1):
                self.sequence_numbers[src] = seq_num
                self.link_state[src] = neighbors
                self.update_graph()
                # Flood to all neighbors except incoming
                self.flood(packet.content, exclude_port=port)
        elif packet.is_traceroute:
            # Forward traceroute based on forwarding table
            next_hop = self.forwarding_table.get(packet.dst_addr)
            if next_hop:
                self.send(next_hop[0], packet)

    def handle_new_link(self, port, endpoint, cost):
        """Handle new link."""
        # Add bidirectional link cost
        self.link_state.setdefault(self.addr, {})[endpoint] = cost
        self.link_state.setdefault(endpoint, {})[self.addr] = cost
        self.sequence_numbers[self.addr] += 1
        self.broadcast_link_state()

    def handle_remove_link(self, port):
        """Handle removed link."""
        # Remove both directions
        neighbors = self.link_state.get(self.addr, {})
        for neighbor in list(neighbors):
            if self.get_port_for_neighbor(neighbor) is None:
                del neighbors[neighbor]
                # Also remove reverse link
                if neighbor in self.link_state:
                    self.link_state[neighbor].pop(self.addr, None)
        self.sequence_numbers[self.addr] += 1
        self.update_graph()
        self.broadcast_link_state()

    def handle_time(self, time_ms):
        """Periodic heartbeat to rebroadcast own LS."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.sequence_numbers[self.addr] += 1
            self.broadcast_link_state()

    def update_graph(self):
        """Update the network graph based on the current link state."""
        self.graph.clear()
        for router, neighbors in self.link_state.items():
            for neighbor, cost in neighbors.items():
                # Add undirected edge
                self.graph.add_edge(router, neighbor, weight=cost)
        self.update_forwarding_table()

    def update_forwarding_table(self):
        """Compute shortest paths and build forwarding table."""
        self.forwarding_table.clear()
        try:
            paths = nx.single_source_dijkstra_path(self.graph, self.addr)
            for dest, path in paths.items():
                if len(path) < 2:
                    continue
                next_hop = path[1]
                port = self.get_port_for_neighbor(next_hop)
                cost = self.graph[self.addr][next_hop]["weight"]
                if port is not None:
                    self.forwarding_table[dest] = (port, cost)
        except nx.NetworkXNoPath:
            pass

    def broadcast_link_state(self, content=None):
        """Broadcast the link state of this router to all neighbors."""
        if content is None:
            info = {
                "src": self.addr,
                "seq_num": self.sequence_numbers[self.addr],
                "neighbors": self.link_state.get(self.addr, {})
            }
            content = json.dumps(info)
        # Send to all current neighbors
        for neighbor in self.link_state.get(self.addr, {}):
            port = self.get_port_for_neighbor(neighbor)
            if port is not None:
                pkt = Packet(kind=Packet.ROUTING, src_addr=self.addr,
                             dst_addr=neighbor, content=content)
                self.send(port, pkt)

    def flood(self, content, exclude_port):
        """Forward LS packet to all neighbors except the one it came from."""
        for neighbor in self.link_state.get(self.addr, {}):
            port = self.get_port_for_neighbor(neighbor)
            if port is not None and port != exclude_port:
                pkt = Packet(kind=Packet.ROUTING, src_addr=self.addr,
                             dst_addr=neighbor, content=content)
                self.send(port, pkt)

    def get_port_for_neighbor(self, neighbor):
        """Get the port for a given neighbor."""
        for port, link in self.links.items():
            if link.e1 == neighbor or link.e2 == neighbor:
                return port
        return None

    def __repr__(self):
        return f"LSrouter(addr={self.addr}, LSDB={self.link_state})"