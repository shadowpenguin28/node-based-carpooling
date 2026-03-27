from .models import Trip, TripNode, TripPassenger, CarPoolRequest, DriverOffer
from core import graph


def create_trip(driver, start_node, end_node, max_passengers):
    try:
        if driver.role != "driver" or max_passengers <= 0:
            return None
    except Exception:
        return None

    route = graph.find_shortest_path(start_node=start_node, end_node=end_node)
    if route is None:
        return None

    trip = Trip(
        driver=driver,
        max_passengers=max_passengers,
        start_node=start_node,
        end_node=end_node,
    )
    trip.save()
    TripNode.objects.bulk_create([
        TripNode(trip=trip, node=route[i], order=i)
        for i in range(len(route))
    ])
    return trip


def add_passenger_to_trip(passenger, trip: Trip, pickup_node, drop_node, fare=None):
    try:
        if passenger.role != "passenger":
            return None
    except Exception:
        return None

    if not trip.can_board_more:
        return None

    tp = TripPassenger(
        trip=trip,
        pickup=pickup_node,
        drop=drop_node,
        passenger=passenger,
        boarding_status=TripPassenger.BoardingStatus.PENDING,
        fare=fare,
    )
    tp.save()
    return tp


def find_matching_trips(pickup, drop):
    matching = []
    trips = Trip.objects.filter(status__in=['planned', 'active'])

    for trip in trips:
        if not trip.can_board_more:
            continue

        reachable = set()
        for node in trip.get_remaining_route():
            for n in graph.nodes_in_n_hops(node, 2):
                reachable.add(n)

        if pickup in reachable and drop in reachable:
            matching.append(trip)

    return matching


def calculate_detour(trip: Trip, pickup, drop):
    remaining = trip.get_remaining_route()
    if len(remaining) < 2:
        return None

    path_pickup_to_drop = graph.find_shortest_path(pickup, drop)
    if path_pickup_to_drop is None:
        return None

    # Depart candidates: route nodes from which the driver CAN REACH the pickup
    depart_candidates = []
    for i, node in enumerate(remaining):
        if node == pickup:
            depart_candidates.append((i, node))
        else:
            reachable = graph.nodes_in_n_hops(node, 2)
            if pickup in reachable:
                depart_candidates.append((i, node))

    # Rejoin candidates: route nodes that the drop CAN REACH
    drop_reachable = graph.nodes_in_n_hops(drop, 2)
    rejoin_candidates = [
        (j, node) for j, node in enumerate(remaining)
        if node in drop_reachable or node == drop
    ]

    best = None

    for i, depart_node in depart_candidates:
        path_to_pickup = graph.find_shortest_path(depart_node, pickup)
        if path_to_pickup is None:
            continue

        for j, rejoin_node in rejoin_candidates:
            if j <= i:
                continue

            path_from_drop = graph.find_shortest_path(drop, rejoin_node)
            if path_from_drop is None:
                continue

            new_hops = (
                (len(path_to_pickup) - 1)
                + (len(path_pickup_to_drop) - 1)
                + (len(path_from_drop) - 1)
            )
            orig_hops = j - i
            detour = new_hops - orig_hops

            if best is None or detour < best['detour']:
                best = {
                    'detour': detour,
                    'depart_idx': i,
                    'rejoin_idx': j,
                    'path_to_pickup': path_to_pickup,
                    'path_pickup_to_drop': path_pickup_to_drop,
                    'path_from_drop': path_from_drop,
                }

    return best


def build_new_route(remaining: list, detour_info: dict):
    i = detour_info['depart_idx']
    j = detour_info['rejoin_idx']
    return (
        remaining[:i + 1]
        + detour_info['path_to_pickup'][1:]
        + detour_info['path_pickup_to_drop'][1:]
        + detour_info['path_from_drop'][1:]
        + remaining[j + 1:]
    )


def apply_detour_to_trip(trip: Trip, detour_info: dict):
    remaining = trip.get_remaining_route()
    depart_node = remaining[detour_info['depart_idx']]
    depart_order = TripNode.objects.get(trip=trip, node=depart_node).order

    new_route = build_new_route(remaining, detour_info)
    tail = new_route[detour_info['depart_idx'] + 1:]

    TripNode.objects.filter(trip=trip, order__gt=depart_order).delete()
    TripNode.objects.bulk_create([
        TripNode(trip=trip, node=node, order=depart_order + 1 + idx)
        for idx, node in enumerate(tail)
    ])


def calculate_fare(trip: Trip, passenger_pickup, passenger_drop,
                   detour_info: dict, price_per_hop: float, base_fee: float):
    remaining = trip.get_remaining_route()
    new_route = build_new_route(remaining, detour_info)

    pickup_idx = next(
        (i for i, n in enumerate(new_route) if n.id == passenger_pickup.id), None
    )
    drop_idx = next(
        (i for i, n in enumerate(new_route) if n.id == passenger_drop.id), None
    )

    if pickup_idx is None or drop_idx is None or pickup_idx >= drop_idx:
        return None

    existing_passengers = TripPassenger.objects.filter(
        trip=trip,
        boarding_status__in=[
            TripPassenger.BoardingStatus.PENDING,
            TripPassenger.BoardingStatus.BOARDED,
        ],
    )

    segments = []
    for tp in existing_passengers:
        p_start = next(
            (i for i, n in enumerate(new_route) if n.id == tp.pickup.id), None
        )
        p_end = next(
            (i for i, n in enumerate(new_route) if n.id == tp.drop.id), None
        )
        if p_start is None and tp.boarding_status == TripPassenger.BoardingStatus.BOARDED:
            p_start = 0
        if p_start is None and tp.boarding_status == TripPassenger.BoardingStatus.PENDING:
            p_start = 0
        if p_start is not None and p_end is not None and p_start < p_end:
            segments.append((p_start, p_end))

    segments.append((pickup_idx, drop_idx))

    total = 0.0
    for hop in range(pickup_idx, drop_idx):
        n_i = sum(1 for (board, alight) in segments if board <= hop < alight)
        if n_i > 0:
            total += 1.0 / n_i

    return round(price_per_hop * total + base_fee, 2)

def calculate_final_fare(trip: Trip, trip_passenger: TripPassenger,
                          price_per_hop: float, base_fee: float):
    """
    Recalculates fare at drop-off time using the actual stored route.
    Accounts for any detours added after the passenger boarded.
    """
    route = trip.get_route()

    pickup_idx = next(
        (i for i, n in enumerate(route) if n.id == trip_passenger.pickup.id), None
    )
    drop_idx = next(
        (i for i, n in enumerate(route) if n.id == trip_passenger.drop.id), None
    )

    if pickup_idx is None or drop_idx is None or pickup_idx >= drop_idx:
        return None

    all_passengers = TripPassenger.objects.filter(
        trip=trip,
        boarding_status__in=[
            TripPassenger.BoardingStatus.PENDING,
            TripPassenger.BoardingStatus.BOARDED,
            TripPassenger.BoardingStatus.DROPPED,
        ]
    )

    segments = []
    for tp in all_passengers:
        p_start = next((i for i, n in enumerate(route) if n.id == tp.pickup.id), None)
        p_end = next((i for i, n in enumerate(route) if n.id == tp.drop.id), None)
        if p_start is not None and p_end is not None and p_start < p_end:
            segments.append((p_start, p_end))

    total = 0.0
    for hop in range(pickup_idx, drop_idx):
        n_i = sum(1 for (board, alight) in segments if board <= hop < alight)
        if n_i > 0:
            total += 1.0 / n_i

    return round(price_per_hop * total + base_fee, 2)