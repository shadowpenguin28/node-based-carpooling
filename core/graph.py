from .models import Node, Edge
from collections import deque

def get_neighbours(node: Node):
    return Node.objects.filter(incoming__source = node)

def find_shortest_path(start_node: Node, end_node: Node):
    if start_node == end_node:
        return [start_node]
    visited = {start_node.id}
    queue = deque([(start_node, [start_node])])

    while queue:
        current, path = queue.popleft()
        for neighbour in get_neighbours(current):
            if neighbour.id == end_node.id:
                return path + [neighbour]
            if neighbour.id not in visited:
                visited.add(neighbour.id)
                queue.append((neighbour, path + [neighbour]))
    
    # No paths found
    return None

def nodes_in_n_hops(node: Node, n: int):
    visited = {node}
    queue = deque([(node, 0)])
    
    while queue:
        current, depth = queue.popleft()
        if depth >= n:
            continue

        for neighbour in get_neighbours(current):
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append((neighbour, depth+1))
    
    return visited



    

