####################################################
# DVrouter.py
# Name:
# HUID:
#####################################################

from router import Router
import json

INFINITY = 16  # Giá trị infinity cho DV

class DVrouter(Router):
    """Distance vector routing protocol implementation."""

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        # Bảng chi phí đến các đích: {dest: (cost, next_hop_port)}
        self.forwarding_table = {}

        # Distance vector của chính router này: {dest: cost}
        self.distance_vector = {self.addr: 0}

        # Lưu vector của hàng xóm: {neighbor_addr: {dest: cost}}
        self.neighbor_vectors = {}

        # Lưu thông tin các link trực tiếp: {port: (neighbor_addr, cost)}
        self.links = {}

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        if packet.is_traceroute:
            # Gói dữ liệu: chuyển tiếp nếu biết đường đi
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst][1]
                self.send(out_port, packet)
        else:
            # Gói định tuyến: cập nhật vector của hàng xóm
            content = json.loads(packet.content)
            neighbor = packet.src_addr
            self.neighbor_vectors[neighbor] = content

            # Cập nhật lại distance vector và forwarding table
            changed = self.update_distance_vector()
            if changed:
                self.broadcast_distance_vector()

    def handle_new_link(self, port, endpoint, cost):
        """Handle new link."""
        self.links[port] = (endpoint, cost)
        if endpoint not in self.neighbor_vectors:
            self.neighbor_vectors[endpoint] = {}
        changed = self.update_distance_vector()
        if changed:
            self.broadcast_distance_vector()

    def handle_remove_link(self, port):
        """Handle removed link."""
        if port in self.links:
            neighbor, _ = self.links[port]
            del self.links[port]
            if neighbor in self.neighbor_vectors:
                del self.neighbor_vectors[neighbor]
            changed = self.update_distance_vector()
            if changed:
                self.broadcast_distance_vector()

    def handle_time(self, time_ms):
        """Handle current time."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_distance_vector()

    def broadcast_distance_vector(self):
        # Gửi distance vector của mình cho tất cả hàng xóm, áp dụng poison reverse
        for port, (neighbor, _) in self.links.items():
            poisoned_vector = {}
            for dest, cost in self.distance_vector.items():
                # Nếu đường tốt nhất đến dest là qua neighbor này, báo INFINITY (poison reverse)
                if dest != neighbor and dest in self.forwarding_table and self.forwarding_table[dest][1] == port:
                    poisoned_vector[dest] = INFINITY
                else:
                    poisoned_vector[dest] = cost
            content = json.dumps(poisoned_vector)
            from packet import Packet
            pkt = Packet(Packet.ROUTING, self.addr, neighbor, content)
            self.send(port, pkt)

    def update_distance_vector(self):
        """Tính lại distance vector và forwarding table. Trả về True nếu có thay đổi."""
        updated = False
        new_distance_vector = {self.addr: 0}
        new_forwarding_table = {}

        # Tập hợp tất cả đích có thể biết
        destinations = set([self.addr])
        for vec in self.neighbor_vectors.values():
            destinations.update(vec.keys())
        for _, (neighbor, _) in self.links.items():
            destinations.add(neighbor)

        for dest in destinations:
            if dest == self.addr:
                continue
            min_cost = INFINITY
            min_port = None
            # Xét từng hàng xóm
            for port, (neighbor, link_cost) in self.links.items():
                neighbor_vec = self.neighbor_vectors.get(neighbor, {})
                neighbor_cost = neighbor_vec.get(dest, INFINITY)
                # Nếu neighbor_cost >= INFINITY thì coi như không có đường
                total_cost = link_cost + neighbor_cost
                # Nếu dest là neighbor trực tiếp thì ưu tiên đường trực tiếp
                if dest == neighbor:
                    total_cost = link_cost
                if total_cost < min_cost:
                    min_cost = total_cost
                    min_port = port
            if min_cost < INFINITY:
                new_distance_vector[dest] = min_cost
                new_forwarding_table[dest] = (min_cost, min_port)

        # Kiểm tra thay đổi
        if new_distance_vector != self.distance_vector or new_forwarding_table != self.forwarding_table:
            self.distance_vector = new_distance_vector
            self.forwarding_table = new_forwarding_table
            updated = True
        return updated

    def __repr__(self):
        return f"DVrouter(addr={self.addr}, dv={self.distance_vector})"