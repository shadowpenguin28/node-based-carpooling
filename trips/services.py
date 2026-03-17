from .models import Trip, TripNode, TripPassenger
from core import graph
from django.db.models import Q

def create_trip(driver, start_node, end_node, max_passengers):
    try:
        if driver.role != "driver" or max_passengers <= 0: 
            return None
    except:
        return None

    trip = Trip(
        driver = driver, 
        max_passengers=max_passengers, 
        start_node=start_node, 
        end_node=end_node
    )

    # generate route
    route = graph.find_shortest_path(start_node=start_node, end_node=end_node)
    tripnodes = []
    if route != None:
        for i in range(len(route)):
            trip_node = TripNode(trip = trip, node = route[i], order=i)
            tripnodes.append(trip_node)
    else:
        return None

    # save the entries if no errors encountered
    trip.save()
    TripNode.objects.bulk_create(tripnodes)
    return trip

def add_passenger_to_trip(passenger, trip: Trip, pickup_node, drop_node):
    try:
        if passenger.role != "passenger":
            return "Invalid User type"
    except:
        return "Invalid data"
    
    if not trip.can_board_more:
        return None
    
    trip_passenger = TripPassenger(trip=trip, pickup=pickup_node, drop=drop_node, passenger=passenger)
    trip_passenger.boarding_status = TripPassenger.BoardingStatus.PENDING

    trip_passenger.save()

    return trip_passenger

def find_matching_trips(pickup, drop):
    matching_trips = []
    trips = Trip.objects.filter(status__in = ['planned', 'active'])

    for trip in trips:
        if not trip.can_board_more:
            continue

        remaining_route = trip.get_remaining_route()

        reachable_nodes = set()
        for node in remaining_route:
            available = graph.nodes_in_n_hops(node, 2)

            for n in available:
                reachable_nodes.add(n)
        
        if pickup in reachable_nodes and drop in reachable_nodes:
            matching_trips.append(trip)
    
    return matching_trips

def calculate_detour(trip: Trip, pickup, drop):
    """
    Finds the optimal insertion points for pickup and drop in the remaining route.
    Returns dict with detour info, or None if no valid insertion exists.
    
    For each pair of insertion points (i for pickup, j for drop where j >= i):
      - Compute path: route[i] → pickup → route[i+1]  (pickup detour)
      - Compute path: route[j] → drop → route[j+1]    (drop detour)
      - Total detour = extra hops added by both insertions
    Pick the pair that minimizes total detour.
    """
    remaining_route = trip.get_remaining_route()

    if len(remaining_route) < 2:
        return None

    best = None

    for i in range(len(remaining_route) - 1):
        # Pickup detour: route[i] → pickup → route[i+1]
        path_to_pickup = graph.find_shortest_path(remaining_route[i], pickup)
        if path_to_pickup is None:
            continue
        path_from_pickup = graph.find_shortest_path(pickup, remaining_route[i + 1])
        if path_from_pickup is None:
            continue

        # Extra hops from pickup insertion
        # Original: 1 hop (route[i] → route[i+1])
        # New: (route[i] → pickup) + (pickup → route[i+1])
        pickup_extra = (len(path_to_pickup) - 1) + (len(path_from_pickup) - 1) - 1

        for j in range(i, len(remaining_route) - 1):
            # Drop detour: route[j] → drop → route[j+1]
            path_to_drop = graph.find_shortest_path(remaining_route[j], drop)
            if path_to_drop is None:
                continue
            path_from_drop = graph.find_shortest_path(drop, remaining_route[j + 1])
            if path_from_drop is None:
                continue

            drop_extra = (len(path_to_drop) - 1) + (len(path_from_drop) - 1) - 1
            total_detour = pickup_extra + drop_extra

            if best is None or total_detour < best['detour']:
                best = {
                    'detour': total_detour,
                    'pickup_insert_after': i,
                    'drop_insert_after': j,
                    'path_to_pickup': path_to_pickup,
                    'path_from_pickup': path_from_pickup,
                    'path_to_drop': path_to_drop,
                    'path_from_drop': path_from_drop,
                }

    return best


def calculate_fare(trip, passenger_pickup, passenger_drop, price_per_hop, base_fee):
    """
    Fare formula: fare = price_per_hop × Σ(1/nᵢ) + base_fee
    
    nᵢ = number of passengers in the car at hop i (including this passenger).
    Sum is over all hops where this passenger is onboard.
    """
    route = trip.get_route()

    # Find indices of pickup and drop in the route
    try:
        pickup_idx = next(i for i, node in enumerate(route) if node.id == passenger_pickup.id)
        drop_idx = next(i for i, node in enumerate(route) if node.id == passenger_drop.id)
    except StopIteration:
        return None  # pickup or drop not found on route

    if pickup_idx >= drop_idx:
        return None

    # Get all active passengers and find their segments on the route
    trip_passengers = TripPassenger.objects.filter(
        trip=trip,
        boarding_status__in=['pending', 'boarded']
    )

    passenger_segments = []
    for tp in trip_passengers:
        try:
            p_start = next(i for i, node in enumerate(route) if node.id == tp.pickup.id)
            p_end = next(i for i, node in enumerate(route) if node.id == tp.drop.id)
            passenger_segments.append((p_start, p_end))
        except StopIteration:
            continue

    # Include the new passenger's segment
    passenger_segments.append((pickup_idx, drop_idx))

    # Sum 1/nᵢ for each hop where this passenger is onboard
    total = 0
    for hop in range(pickup_idx, drop_idx):
        # A passenger is onboard at hop i if pickup <= i and drop > i
        n_i = sum(1 for (p, d) in passenger_segments if p <= hop and d > hop)
        if n_i > 0:
            total += 1.0 / n_i

    fare = price_per_hop * total + base_fee
    return round(fare, 2)
