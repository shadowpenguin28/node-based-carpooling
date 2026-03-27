from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsDriver, IsPassenger, IsAdmin
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from decimal import Decimal

from .serializers import TripCreateSerializer, CarPoolRequestSerializer
from . import services
from .models import Trip, TripPassenger, TripNode, CarPoolRequest, DriverOffer, Transaction

PRICE_PER_HOP = 10
BASE_FEE = 5


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def create_trip_view(request):
    serializer = TripCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(data={"errors": "Invalid data"}, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    trip = services.create_trip(
        driver=request.user,
        start_node=data['start_node'],
        end_node=data['end_node'],
        max_passengers=data['max_passengers']
    )
    if trip is None:
        return Response(data={"error": "Trip could not be created"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(data={"message": "success"}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def start_trip_view(request, trip_id):
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if trip.status != Trip.Status.PLANNED:
        return Response(data={"errors": "Trip cannot be started"}, status=status.HTTP_400_BAD_REQUEST)
    if request.user != trip.driver:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    trip.start_trip()
    return Response(data={"message": "Trip successfully started"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def advance_trip_view(request, trip_id):
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user != trip.driver:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    if trip.current_node == trip.end_node:
        # Verify all passengers have sufficient balance before completing
        trip_passengers = TripPassenger.objects.filter(
            trip=trip,
            boarding_status__in=[
                TripPassenger.BoardingStatus.PENDING,
                TripPassenger.BoardingStatus.BOARDED,
            ]
        )
        for tp in trip_passengers:
            if tp.fare and Decimal(str(tp.fare)) > tp.passenger.wallet_balance:
                return Response(
                    data={"errors": f"Passenger {tp.passenger.first_name} has insufficient wallet balance"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Deduct fares from passengers and accumulate driver earnings
        total_earnings = Decimal('0')
        for tp in trip_passengers:
            if tp.fare:
                fare = Decimal(str(tp.fare))
                tp.passenger.wallet_balance -= fare
                tp.passenger.save()
                total_earnings += fare
                Transaction.objects.create(
                    user=tp.passenger,
                    trip=trip,
                    type='fare_deduction',
                    amount=fare,
                )
                tp.drop_off()

        # Credit driver
        if total_earnings > 0:
            trip.driver.wallet_balance += total_earnings
            trip.driver.save()
            Transaction.objects.create(
                user=trip.driver,
                trip=trip,
                type='driver_earning',
                amount=total_earnings,
            )

        # Total earnings including passengers already dropped off during the trip
        from django.db.models import Sum
        grand_total = Transaction.objects.filter(
            trip=trip, user=trip.driver, type='driver_earning'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        trip.complete_trip()
        return Response(data={"message": f"Trip completed! Total earned: ₹{grand_total}"}, status=status.HTTP_200_OK)

    # Check: must board all pending passengers whose pickup is current node
    unboarded = TripPassenger.objects.filter(
        trip=trip,
        pickup=trip.current_node,
        boarding_status=TripPassenger.BoardingStatus.PENDING,
    )
    if unboarded.exists():
        names = ', '.join(f"{tp.passenger.first_name} {tp.passenger.last_name}" for tp in unboarded)
        return Response(
            data={"errors": f"Must board passengers at {trip.current_node.name} first: {names}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check: must drop off all boarded passengers whose drop is current node
    undropped = TripPassenger.objects.filter(
        trip=trip,
        drop=trip.current_node,
        boarding_status=TripPassenger.BoardingStatus.BOARDED,
    )
    if undropped.exists():
        names = ', '.join(f"{tp.passenger.first_name} {tp.passenger.last_name}" for tp in undropped)
        return Response(
            data={"errors": f"Must drop off passengers at {trip.current_node.name} first: {names}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    next_node = trip.advance_to_next_node()
    return Response(data={"message": f"Advanced to {next_node.name}"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def cancel_trip_view(request, trip_id):
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user != trip.driver:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    if trip.status != Trip.Status.PLANNED:
        return Response(data={"message": "Trip cannot be cancelled!"}, status=status.HTTP_304_NOT_MODIFIED)

    trip.cancel_trip()
    return Response(data={"message": "Cancelled!"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPassenger])
def top_up_wallet(request):
    amount = request.data.get('amount')
    if not amount:
        return Response(data={"errors": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        return Response(data={"errors": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

    request.user.wallet_balance += amount
    request.user.save()

    Transaction.objects.create(
        user=request.user,
        trip=None,
        type='top_up',
        amount=amount,
    )

    return Response(data={
        "message": "Wallet topped up",
        "new_balance": request.user.wallet_balance,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_transactions(request):
    txns = Transaction.objects.filter(user=request.user).order_by('-created_at')
    data = [
        {
            'type': t.type,
            'amount': t.amount,
            'trip': t.trip.id if t.trip else None,
            'created_at': t.created_at,
        }
        for t in txns
    ]
    return Response(data={
        "balance": request.user.wallet_balance,
        "transactions": data,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPassenger])
def create_carpool_request(request):
    # Check if passenger is already on an active trip
    active_trip = TripPassenger.objects.filter(
        passenger=request.user,
        boarding_status__in=[TripPassenger.BoardingStatus.PENDING, TripPassenger.BoardingStatus.BOARDED],
        trip__status__in=['planned', 'active'],
    ).exists()
    if active_trip:
        return Response(
            data={"errors": "You are already on an active trip. Complete it before requesting a new ride."},
            status=status.HTTP_400_BAD_REQUEST
        )
    serializer = CarPoolRequestSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        CarPoolRequest.objects.create(
            passenger=request.user,
            pickup=data['pickup'],
            drop=data['drop']
        )
        return Response(data={"message": "Carpool request created"}, status=status.HTTP_201_CREATED)
    return Response(data={'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPassenger])
def view_driver_offers(request, cr_id):
    try:
        cr_req = CarPoolRequest.objects.get(pk=cr_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors": "Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user != cr_req.passenger:
        return Response(data={"errors": "Not your Carpool Request"}, status=status.HTTP_403_FORBIDDEN)

    offers = DriverOffer.objects.filter(carpool_request_id=cr_id)
    if not offers.exists():
        return Response(data={"message": "No offers yet"}, status=status.HTTP_200_OK)

    response_data = {
        offer.id: {
            'driver': f"{offer.driver.first_name} {offer.driver.last_name}",
            'trip': offer.trip.id,
            'fare': offer.fare,
            'detour': offer.detour,
            'status': offer.status,
        }
        for offer in offers
    }
    return Response(data=response_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPassenger])
def accept_driver_offer(request, req_id, offer_id):
    try:
        req = CarPoolRequest.objects.get(pk=req_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors": "Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user != req.passenger:
        return Response(data={"errors": "Not your request!"}, status=status.HTTP_403_FORBIDDEN)

    try:
        offer = DriverOffer.objects.get(pk=offer_id)
    except DriverOffer.DoesNotExist:
        return Response(data={"errors": "Offer not found"}, status=status.HTTP_404_NOT_FOUND)

    if offer.carpool_request != req:
        return Response(data={"errors": "Invalid offer"}, status=status.HTTP_400_BAD_REQUEST)

    if not offer.trip.can_board_more:
        return Response(data={"errors": "Trip is full"}, status=status.HTTP_400_BAD_REQUEST)

    # Check passenger has enough balance to cover the fare
    if Decimal(str(offer.fare)) > request.user.wallet_balance:
        return Response(data={"errors": "Insufficient wallet balance"}, status=status.HTTP_400_BAD_REQUEST)

    offer.status = DriverOffer.Status.ACCEPTED
    offer.save()

    req.status = CarPoolRequest.Status.MATCHED
    req.save()

    DriverOffer.objects.filter(
        carpool_request=req, status='pending'
    ).exclude(pk=offer.pk).update(status='rejected')

    detour_info = services.calculate_detour(offer.trip, req.pickup, req.drop)
    if detour_info is None:
        raise Exception("Could not calculate detour — rolling back")

    services.apply_detour_to_trip(offer.trip, detour_info)

    services.add_passenger_to_trip(
        passenger=req.passenger,
        trip=offer.trip,
        pickup_node=req.pickup,
        drop_node=req.drop,
        fare=offer.fare,
    )

    return Response(data={
        "message": "Offer accepted!",
        "driver": f"{offer.driver.first_name} {offer.driver.last_name}",
        "detour": offer.detour,
        "fare": offer.fare,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPassenger])
def cancel_carpool_request(request, cr_id):
    try:
        req = CarPoolRequest.objects.get(pk=cr_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors": "Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if req.passenger != request.user:
        return Response(data={"errors": "Not your carpool request"}, status=status.HTTP_403_FORBIDDEN)

    if req.status == CarPoolRequest.Status.MATCHED:
        return Response(data={"errors": "Cannot cancel, already matched!"}, status=status.HTTP_400_BAD_REQUEST)
    if req.status == CarPoolRequest.Status.CANCELLED:
        return Response(data={"errors": "Already cancelled!"}, status=status.HTTP_400_BAD_REQUEST)

    req.status = CarPoolRequest.Status.CANCELLED
    req.save()
    return Response(data={"message": "Cancelled carpool request"}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDriver])
def view_carpool_requests(request):
    driver_trips = Trip.objects.filter(driver=request.user, status__in=['planned', 'active'])
    if not driver_trips.exists():
        return Response(data={"message": "No active trips"}, status=status.HTTP_200_OK)

    pending_requests = CarPoolRequest.objects.filter(status='pending')
    matching = []

    for cr in pending_requests:
        matched_trips = services.find_matching_trips(cr.pickup, cr.drop)
        for trip in matched_trips:
            if trip.driver != request.user:
                continue
            detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
            fare = services.calculate_fare(
                trip, cr.pickup, cr.drop, detour_info, PRICE_PER_HOP, BASE_FEE
            ) if detour_info else None
            matching.append({
                'request_id': cr.id,
                'passenger': f"{cr.passenger.first_name} {cr.passenger.last_name}",
                'pickup': cr.pickup.name,
                'drop': cr.drop.name,
                'trip_id': trip.id,
                'detour': detour_info['detour'] if detour_info else None,
                'estimated_fare': fare,
            })

    if not matching:
        return Response(data={"message": "No matching requests found"}, status=status.HTTP_200_OK)

    return Response(data=matching, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def create_driver_offer(request, req_id):
    try:
        cr = CarPoolRequest.objects.get(pk=req_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors": "Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if cr.status != CarPoolRequest.Status.PENDING:
        return Response(data={"errors": "Request is no longer pending"}, status=status.HTTP_400_BAD_REQUEST)

    trip_id = request.data.get('trip_id')
    if not trip_id:
        return Response(data={"errors": "trip_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found or not yours"}, status=status.HTTP_404_NOT_FOUND)

    if DriverOffer.objects.filter(carpool_request=cr, driver=request.user).exists():
        return Response(data={"errors": "You already offered for this request"}, status=status.HTTP_400_BAD_REQUEST)

    detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
    if detour_info is None:
        return Response(data={"errors": "Cannot reach pickup/drop from your route"}, status=status.HTTP_400_BAD_REQUEST)

    fare = services.calculate_fare(trip, cr.pickup, cr.drop, detour_info, PRICE_PER_HOP, BASE_FEE)
    if fare is None:
        return Response(data={"errors": "Could not calculate fare"}, status=status.HTTP_400_BAD_REQUEST)

    offer = DriverOffer.objects.create(
        driver=request.user,
        carpool_request=cr,
        trip=trip,
        fare=fare,
        detour=detour_info['detour'],
    )

    return Response(data={
        "message": "Offer created",
        "offer_id": offer.id,
        "fare": offer.fare,
        "detour": offer.detour,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDriver])
def fetch_driver_trips(request):
    qs = Trip.objects.filter(driver=request.user)
    if not qs.exists():
        return Response(data={"message": "No trips found"}, status=status.HTTP_404_NOT_FOUND)

    trips = [
        {
            'id': trip.id,
            'status': trip.status,
            'start_node': trip.start_node.name,
            'end_node': trip.end_node.name,
            'current_node': trip.current_node.name if trip.current_node else None,
            'passenger_count': trip.active_passenger_count,
            'max_passengers': trip.max_passengers,
            'created_at': trip.created_at,
        }
        for trip in qs
    ]
    return Response(data=trips, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_view_active_trips(request):
    qs = Trip.objects.filter(status="active")
    if not qs.exists():
        return Response(data={"message": "No active trips"})

    trips = [
        {
            'id': trip.id,
            'driver': f"{trip.driver.first_name} {trip.driver.last_name}",
            'passengers': [
                {
                    'name': f"{p.passenger.first_name} {p.passenger.last_name}",
                    'status': p.boarding_status,
                    'pickup': p.pickup.name,
                    'drop': p.drop.name,
                }
                for p in TripPassenger.objects.filter(trip=trip)
            ],
            'start_node': trip.start_node.name,
            'end_node': trip.end_node.name,
            'current_node': trip.current_node.name if trip.current_node else None,
            'passenger_count': trip.active_passenger_count,
            'max_passengers': trip.max_passengers,
            'created_at': trip.created_at,
        }
        for trip in qs
    ]
    return Response(data=trips, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDriver])
def trip_dashboard(request, trip_id):
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if trip.driver != request.user:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    route = [
        {'order': tn.order, 'node': tn.node.name, 'node_id': tn.node.id}
        for tn in TripNode.objects.filter(trip=trip).order_by('order')
    ]
    passengers = [
        {
            'name': f"{tp.passenger.first_name} {tp.passenger.last_name}",
            'boarding_status': tp.boarding_status,
            'pickup': tp.pickup.name,
            'drop': tp.drop.name,
            'fare': tp.fare,
        }
        for tp in TripPassenger.objects.filter(trip=trip)
    ]
    offers = [
        {
            'offer_id': offer.id,
            'passenger': f"{offer.carpool_request.passenger.first_name} {offer.carpool_request.passenger.last_name}",
            'pickup': offer.carpool_request.pickup.name,
            'drop': offer.carpool_request.drop.name,
            'fare': offer.fare,
            'detour': offer.detour,
            'status': offer.status,
        }
        for offer in DriverOffer.objects.filter(trip=trip, driver=request.user)
    ]

    return Response(data={
        'trip_id': trip.id,
        'status': trip.status,
        'start_node': trip.start_node.name,
        'end_node': trip.end_node.name,
        'current_node': trip.current_node.name if trip.current_node else None,
        'passenger_count': trip.active_passenger_count,
        'max_passengers': trip.max_passengers,
        'route': route,
        'passengers': passengers,
        'offers': offers,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_toggle_service(request):
    from core.models import ServiceConfig
    config, _ = ServiceConfig.objects.get_or_create(pk=1)
    config.is_active = not config.is_active
    config.save()
    state = "active" if config.is_active else "suspended"
    return Response(data={"message": f"Service is now {state}", "is_active": config.is_active}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def board_passenger(request, trip_id, passenger_id):
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if trip.driver != request.user:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    if trip.status != Trip.Status.ACTIVE:
        return Response(data={"errors": "Trip is not active"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tp = TripPassenger.objects.get(trip=trip, passenger_id=passenger_id)
    except TripPassenger.DoesNotExist:
        return Response(data={"errors": "Passenger not on this trip"}, status=status.HTTP_404_NOT_FOUND)

    if tp.boarding_status != TripPassenger.BoardingStatus.PENDING:
        return Response(data={"errors": "Passenger cannot be boarded"}, status=status.HTTP_400_BAD_REQUEST)

    if trip.current_node != tp.pickup:
        return Response(
            data={"errors": f"Driver must be at {tp.pickup.name} to board this passenger"},
            status=status.HTTP_400_BAD_REQUEST
        )

    tp.board()
    return Response(data={
        "message": f"{tp.passenger.first_name} boarded",
        "pickup": tp.pickup.name,
        "drop": tp.drop.name,
        "fare": tp.fare,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def dropoff_passenger(request, trip_id, passenger_id):
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if trip.driver != request.user:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    if trip.status != Trip.Status.ACTIVE:
        return Response(data={"errors": "Trip is not active"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tp = TripPassenger.objects.get(trip=trip, passenger_id=passenger_id)
    except TripPassenger.DoesNotExist:
        return Response(data={"errors": "Passenger not on this trip"}, status=status.HTTP_404_NOT_FOUND)

    if tp.boarding_status != TripPassenger.BoardingStatus.BOARDED:
        return Response(data={"errors": "Passenger is not currently boarded"}, status=status.HTTP_400_BAD_REQUEST)

    if trip.current_node != tp.drop:
        return Response(
            data={"errors": f"Driver must be at {tp.drop.name} to drop off this passenger"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Recalculate fare using the actual route driven so far
    final_fare = services.calculate_final_fare(trip, tp, PRICE_PER_HOP, BASE_FEE)
    if final_fare is None:
        return Response(data={"errors": "Could not calculate final fare"}, status=status.HTTP_400_BAD_REQUEST)

    passenger = tp.passenger
    if Decimal(str(final_fare)) > passenger.wallet_balance:
        return Response(data={"errors": "Passenger has insufficient wallet balance"}, status=status.HTTP_400_BAD_REQUEST)

    # Deduct from passenger
    passenger.wallet_balance -= Decimal(str(final_fare))
    passenger.save()
    Transaction.objects.create(
        user=passenger,
        trip=trip,
        type='fare_deduction',
        amount=Decimal(str(final_fare)),
    )
    trip.driver.wallet_balance += Decimal(str(final_fare))
    trip.driver.save()
    Transaction.objects.create(
        user=trip.driver,
        trip=trip,
        type='driver_earning',
        amount=Decimal(str(final_fare)),
    )

    # Update stored fare and mark as dropped
    tp.fare = final_fare
    tp.save()
    tp.drop_off()

    return Response(data={
        "message": f"{passenger.first_name} dropped off",
        "final_fare": final_fare,
        "passenger_balance": passenger.wallet_balance,
    }, status=status.HTTP_200_OK)

# ── SSR pages ────────────────────────────────────────────────────────────────

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from core.models import Node


@login_required
def driver_dashboard_page(request):
    if request.user.role != 'driver':
        return render(request, 'trips/driver_dashboard.html', {'error': 'Only drivers can access this page'})

    driver_trips = Trip.objects.filter(driver=request.user).order_by('-created_at')
    trips_data = []

    for trip in driver_trips:
        route_nodes = TripNode.objects.filter(trip=trip).order_by('order')
        current_order = None
        if trip.current_node:
            try:
                current_order = TripNode.objects.get(trip=trip, node=trip.current_node).order
            except TripNode.DoesNotExist:
                pass

        route = [
            {
                'order': tn.order,
                'name': tn.node.name,
                'is_current': current_order is not None and tn.order == current_order,
                'is_passed': current_order is not None and tn.order < current_order,
            }
            for tn in route_nodes
        ]
        passengers = [
            {
                'id': tp.passenger.id,
                'name': f"{tp.passenger.first_name} {tp.passenger.last_name}",
                'boarding_status': tp.boarding_status,
                'pickup': tp.pickup.name,
                'drop': tp.drop.name,
                'fare': tp.fare,
            }
            for tp in TripPassenger.objects.filter(trip=trip)
        ]
        offers = [
            {
                'passenger': f"{offer.carpool_request.passenger.first_name} {offer.carpool_request.passenger.last_name}",
                'pickup': offer.carpool_request.pickup.name,
                'drop': offer.carpool_request.drop.name,
                'fare': offer.fare,
                'detour': offer.detour,
                'status': offer.status,
            }
            for offer in DriverOffer.objects.filter(trip=trip, driver=request.user)
        ]

        matching_requests = []
        if trip.status in ['planned', 'active'] and trip.can_board_more:
            for cr in CarPoolRequest.objects.filter(status='pending'):
                if trip not in services.find_matching_trips(cr.pickup, cr.drop):
                    continue
                detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
                if detour_info is None:
                    continue  # skip unfeasible matches
                fare = services.calculate_fare(
                    trip, cr.pickup, cr.drop, detour_info, PRICE_PER_HOP, BASE_FEE
                )
                matching_requests.append({
                    'request_id': cr.id,
                    'passenger': f"{cr.passenger.first_name} {cr.passenger.last_name}",
                    'pickup': cr.pickup.name,
                    'drop': cr.drop.name,
                    'detour': detour_info['detour'],
                    'fare': fare,
                })

        trips_data.append({
            'id': trip.id,
            'status': trip.status,
            'start_node': trip.start_node.name,
            'end_node': trip.end_node.name,
            'current_node': trip.current_node.name if trip.current_node else None,
            'passenger_count': trip.active_passenger_count,
            'max_passengers': trip.max_passengers,
            'route': route,
            'passengers': passengers,
            'offers': offers,
            'matching_requests': matching_requests,
        })

    # Build a global pending requests section (across all driver's trips)
    all_pending = CarPoolRequest.objects.filter(status='pending')
    active_driver_trips = Trip.objects.filter(
        driver=request.user, status__in=['planned', 'active']
    )
    pending_requests_data = []
    seen_cr_ids = set()
    for cr in all_pending:
        for trip in active_driver_trips:
            if not trip.can_board_more:
                continue
            if trip not in services.find_matching_trips(cr.pickup, cr.drop):
                continue
            # Already offered?
            already_offered = DriverOffer.objects.filter(
                carpool_request=cr, driver=request.user
            ).exists()
            detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
            if detour_info is None:
                continue  # skip unfeasible matches
            fare = services.calculate_fare(
                trip, cr.pickup, cr.drop, detour_info, PRICE_PER_HOP, BASE_FEE
            )
            key = (cr.id, trip.id)
            if key not in seen_cr_ids:
                seen_cr_ids.add(key)
                pending_requests_data.append({
                    'request_id': cr.id,
                    'passenger': f"{cr.passenger.first_name} {cr.passenger.last_name}",
                    'pickup': cr.pickup.name,
                    'drop': cr.drop.name,
                    'trip_id': trip.id,
                    'trip_route': f"{trip.start_node.name} → {trip.end_node.name}",
                    'detour': detour_info['detour'],
                    'fare': fare,
                    'already_offered': already_offered,
                })

    nodes = Node.objects.all()
    return render(request, 'trips/driver_dashboard.html', {
        'driver_name': f"{request.user.first_name} {request.user.last_name}",
        'trips': trips_data,
        'nodes': nodes,
        'pending_requests': pending_requests_data,
    })


@login_required
def passenger_dashboard_page(request):
    if request.user.role != 'passenger':
        return render(request, 'trips/passenger_dashboard.html', {'error': 'Only passengers can access this page'})

    carpool_requests = CarPoolRequest.objects.filter(passenger=request.user).order_by('-created_at')

    # Enrich each request with its offers
    requests_data = []
    for cr in carpool_requests:
        offers = DriverOffer.objects.filter(carpool_request=cr)
        requests_data.append({
            'id': cr.id,
            'pickup': cr.pickup.name,
            'drop': cr.drop.name,
            'status': cr.status,
            'created_at': cr.created_at,
            'offers': [
                {
                    'id': o.id,
                    'driver': f"{o.driver.first_name} {o.driver.last_name}",
                    'trip_id': o.trip.id,
                    'fare': o.fare,
                    'detour': o.detour,
                    'status': o.status,
                }
                for o in offers
            ],
        })

    # Active trips for this passenger
    active_trips = TripPassenger.objects.filter(
        passenger=request.user,
        boarding_status__in=['pending', 'boarded'],
    ).select_related('trip', 'trip__driver', 'pickup', 'drop')
    active_trips_data = []
    for tp in active_trips:
        trip = tp.trip
        route_nodes = TripNode.objects.filter(trip=trip).order_by('order')
        current_order = None
        if trip.current_node:
            try:
                current_order = TripNode.objects.get(trip=trip, node=trip.current_node).order
            except TripNode.DoesNotExist:
                pass
        route = [
            {
                'name': tn.node.name,
                'is_current': current_order is not None and tn.order == current_order,
                'is_passed': current_order is not None and tn.order < current_order,
            }
            for tn in route_nodes
        ]
        active_trips_data.append({
            'trip_id': trip.id,
            'driver': f"{trip.driver.first_name} {trip.driver.last_name}",
            'status': trip.status,
            'boarding_status': tp.boarding_status,
            'pickup': tp.pickup.name,
            'drop': tp.drop.name,
            'fare': tp.fare,
            'route': route,
        })

    nodes = Node.objects.all()
    return render(request, 'trips/passenger_dashboard.html', {
        'passenger_name': f"{request.user.first_name} {request.user.last_name}",
        'wallet_balance': request.user.wallet_balance,
        'carpool_requests': requests_data,
        'active_trips': active_trips_data,
        'transactions': Transaction.objects.filter(user=request.user).order_by('-created_at'),
        'nodes': nodes,
    })


@login_required
def admin_dashboard_page(request):
    if request.user.role != 'admin':
        return render(request, 'trips/admin_dashboard.html', {'error': 'Only admins can access this page'})

    from core.models import ServiceConfig
    from django.contrib.auth import get_user_model
    User = get_user_model()

    all_trips = Trip.objects.all().order_by('-created_at')
    trips_data = []
    for trip in all_trips:
        passengers = [
            {
                'name': f"{tp.passenger.first_name} {tp.passenger.last_name}",
                'boarding_status': tp.boarding_status,
                'pickup': tp.pickup.name,
                'drop': tp.drop.name,
                'fare': tp.fare,
            }
            for tp in TripPassenger.objects.filter(trip=trip)
        ]
        trips_data.append({
            'id': trip.id,
            'driver': f"{trip.driver.first_name} {trip.driver.last_name}" if trip.driver else "—",
            'status': trip.status,
            'start_node': trip.start_node.name,
            'end_node': trip.end_node.name,
            'current_node': trip.current_node.name if trip.current_node else None,
            'passenger_count': trip.active_passenger_count,
            'max_passengers': trip.max_passengers,
            'created_at': trip.created_at,
            'passengers': passengers,
        })

    service_active = ServiceConfig.is_service_active()
    all_users = User.objects.all().order_by('role', 'first_name')

    return render(request, 'trips/admin_dashboard.html', {
        'admin_name': f"{request.user.first_name} {request.user.last_name}",
        'trips': trips_data,
        'active_count': Trip.objects.filter(status='active').count(),
        'planned_count': Trip.objects.filter(status='planned').count(),
        'completed_count': Trip.objects.filter(status='completed').count(),
        'total_users': User.objects.count(),
        'service_active': service_active,
        'users': all_users,
    })


# ── SSR action views (form POST handlers) ───────────────────────────────────

@login_required
def create_trip_page(request):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    start_id = request.POST.get('start_node')
    end_id = request.POST.get('end_node')
    max_p = request.POST.get('max_passengers')
    try:
        start = Node.objects.get(pk=start_id)
        end = Node.objects.get(pk=end_id)
        trip = services.create_trip(request.user, start, end, int(max_p))
        if trip:
            messages.success(request, f'Trip #{trip.id} created: {start.name} → {end.name}')
        else:
            messages.error(request, 'Could not create trip (check route exists)')
    except Exception as e:
        messages.error(request, f'Error creating trip: {e}')
    return redirect('driver_dashboard_page')


@login_required
def start_trip_page(request, trip_id):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
        if trip.status != Trip.Status.PLANNED:
            messages.error(request, 'Trip cannot be started')
        else:
            trip.start_trip()
            messages.success(request, f'Trip #{trip.id} started!')
    except Trip.DoesNotExist:
        messages.error(request, 'Trip not found')
    return redirect('driver_dashboard_page')


@login_required
def advance_trip_page(request, trip_id):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)

        if trip.current_node == trip.end_node:
            # Complete logic — handle any remaining passengers still on board
            remaining_passengers = TripPassenger.objects.filter(
                trip=trip,
                boarding_status__in=[TripPassenger.BoardingStatus.PENDING, TripPassenger.BoardingStatus.BOARDED],
            )
            completion_earnings = Decimal('0')
            for tp in remaining_passengers:
                if tp.fare:
                    fare = Decimal(str(tp.fare))
                    tp.passenger.wallet_balance -= fare
                    tp.passenger.save()
                    completion_earnings += fare
                    Transaction.objects.create(user=tp.passenger, trip=trip, type='fare_deduction', amount=fare)
                    tp.drop_off()
            if completion_earnings > 0:
                trip.driver.wallet_balance += completion_earnings
                trip.driver.save()
                Transaction.objects.create(user=trip.driver, trip=trip, type='driver_earning', amount=completion_earnings)

            # Calculate total earnings (including passengers already dropped off)
            from django.db.models import Sum
            already_earned = Transaction.objects.filter(
                trip=trip, user=trip.driver, type='driver_earning'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            trip.complete_trip()
            messages.success(request, f'Trip #{trip.id} completed! Total earned: ₹{already_earned}')
        else:
            # Check: must board all pending passengers whose pickup is current node
            unboarded = TripPassenger.objects.filter(
                trip=trip,
                pickup=trip.current_node,
                boarding_status=TripPassenger.BoardingStatus.PENDING,
            )
            if unboarded.exists():
                names = ', '.join(f"{tp.passenger.first_name}" for tp in unboarded)
                messages.error(request, f'Must board passengers at {trip.current_node.name} first: {names}')
                return redirect('driver_dashboard_page')

            # Check: must drop off all boarded passengers whose drop is current node
            undropped = TripPassenger.objects.filter(
                trip=trip,
                drop=trip.current_node,
                boarding_status=TripPassenger.BoardingStatus.BOARDED,
            )
            if undropped.exists():
                names = ', '.join(f"{tp.passenger.first_name}" for tp in undropped)
                messages.error(request, f'Must drop off passengers at {trip.current_node.name} first: {names}')
                return redirect('driver_dashboard_page')

            next_node = trip.advance_to_next_node()
            messages.success(request, f'Advanced to {next_node.name}')
    except Trip.DoesNotExist:
        messages.error(request, 'Trip not found')
    return redirect('driver_dashboard_page')


@login_required
def cancel_trip_page(request, trip_id):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
        if trip.status != Trip.Status.PLANNED:
            messages.error(request, 'Trip cannot be cancelled')
        else:
            trip.cancel_trip()
            messages.success(request, f'Trip #{trip.id} cancelled')
    except Trip.DoesNotExist:
        messages.error(request, 'Trip not found')
    return redirect('driver_dashboard_page')


@login_required
def send_offer_page(request, req_id):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    trip_id = request.POST.get('trip_id')
    try:
        cr = CarPoolRequest.objects.get(pk=req_id, status='pending')
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
        if DriverOffer.objects.filter(carpool_request=cr, driver=request.user).exists():
            messages.error(request, 'You already offered for this request')
            return redirect('driver_dashboard_page')
        detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
        if detour_info is None:
            messages.error(request, 'Cannot reach pickup/drop from your route')
            return redirect('driver_dashboard_page')
        fare = services.calculate_fare(trip, cr.pickup, cr.drop, detour_info, PRICE_PER_HOP, BASE_FEE)
        offer = DriverOffer.objects.create(
            driver=request.user, carpool_request=cr, trip=trip,
            fare=fare, detour=detour_info['detour'],
        )
        messages.success(request, f'Offer sent! Fare: ₹{fare}, Detour: +{offer.detour} hops')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('driver_dashboard_page')


@login_required
def board_passenger_page(request, trip_id, passenger_id):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
        tp = TripPassenger.objects.get(trip=trip, passenger_id=passenger_id)
        if tp.boarding_status != TripPassenger.BoardingStatus.PENDING:
            messages.error(request, 'Passenger cannot be boarded')
        elif trip.current_node != tp.pickup:
            messages.error(request, f'Must be at {tp.pickup.name} to board this passenger')
        else:
            tp.board()
            messages.success(request, f'{tp.passenger.first_name} boarded!')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('driver_dashboard_page')


@login_required
def dropoff_passenger_page(request, trip_id, passenger_id):
    if request.method != 'POST' or request.user.role != 'driver':
        return redirect('driver_dashboard_page')
    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
        tp = TripPassenger.objects.get(trip=trip, passenger_id=passenger_id)
        if tp.boarding_status != TripPassenger.BoardingStatus.BOARDED:
            messages.error(request, 'Passenger is not boarded')
        elif trip.current_node != tp.drop:
            messages.error(request, f'Must be at {tp.drop.name} to drop off')
        else:
            final_fare = services.calculate_final_fare(trip, tp, PRICE_PER_HOP, BASE_FEE)
            if final_fare is None:
                messages.error(request, 'Could not calculate fare')
                return redirect('driver_dashboard_page')
            passenger = tp.passenger
            if Decimal(str(final_fare)) > passenger.wallet_balance:
                messages.error(request, 'Passenger has insufficient balance')
                return redirect('driver_dashboard_page')
            passenger.wallet_balance -= Decimal(str(final_fare))
            passenger.save()
            Transaction.objects.create(user=passenger, trip=trip, type='fare_deduction', amount=Decimal(str(final_fare)))
            trip.driver.wallet_balance += Decimal(str(final_fare))
            trip.driver.save()
            Transaction.objects.create(user=trip.driver, trip=trip, type='driver_earning', amount=Decimal(str(final_fare)))
            tp.fare = final_fare
            tp.save()
            tp.drop_off()
            messages.success(request, f'{passenger.first_name} dropped off! Fare: ₹{final_fare}')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('driver_dashboard_page')


@login_required
def topup_wallet_page(request):
    if request.method != 'POST' or request.user.role != 'passenger':
        return redirect('passenger_dashboard')
    amount = request.POST.get('amount')
    try:
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive')
        request.user.wallet_balance += amount
        request.user.save()
        Transaction.objects.create(user=request.user, trip=None, type='top_up', amount=amount)
        messages.success(request, f'₹{amount} added to wallet')
    except Exception as e:
        messages.error(request, f'Invalid amount: {e}')
    return redirect('passenger_dashboard')


@login_required
def create_request_page(request):
    if request.method != 'POST' or request.user.role != 'passenger':
        return redirect('passenger_dashboard')
    pickup_id = request.POST.get('pickup')
    drop_id = request.POST.get('drop')
    # Check if passenger is already on an active trip
    active_trip = TripPassenger.objects.filter(
        passenger=request.user,
        boarding_status__in=[TripPassenger.BoardingStatus.PENDING, TripPassenger.BoardingStatus.BOARDED],
        trip__status__in=['planned', 'active'],
    ).exists()
    if active_trip:
        messages.error(request, 'You are already on an active trip. Complete it before requesting a new ride.')
        return redirect('passenger_dashboard')
    try:
        pickup = Node.objects.get(pk=pickup_id)
        drop = Node.objects.get(pk=drop_id)
        if pickup == drop:
            messages.error(request, 'Pickup and drop cannot be the same')
            return redirect('passenger_dashboard')
        CarPoolRequest.objects.create(passenger=request.user, pickup=pickup, drop=drop)
        messages.success(request, f'Carpool request created: {pickup.name} → {drop.name}')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('passenger_dashboard')


@login_required
def accept_offer_page(request, req_id, offer_id):
    if request.method != 'POST' or request.user.role != 'passenger':
        return redirect('passenger_dashboard')
    try:
        cr = CarPoolRequest.objects.get(pk=req_id, passenger=request.user)
        offer = DriverOffer.objects.get(pk=offer_id, carpool_request=cr)
        if not offer.trip.can_board_more:
            messages.error(request, 'Trip is full')
            return redirect('passenger_dashboard')
        if Decimal(str(offer.fare)) > request.user.wallet_balance:
            messages.error(request, 'Insufficient wallet balance')
            return redirect('passenger_dashboard')
        offer.status = DriverOffer.Status.ACCEPTED
        offer.save()
        cr.status = CarPoolRequest.Status.MATCHED
        cr.save()
        DriverOffer.objects.filter(carpool_request=cr, status='pending').exclude(pk=offer.pk).update(status='rejected')
        detour_info = services.calculate_detour(offer.trip, cr.pickup, cr.drop)
        if detour_info:
            services.apply_detour_to_trip(offer.trip, detour_info)
        services.add_passenger_to_trip(
            passenger=cr.passenger, trip=offer.trip,
            pickup_node=cr.pickup, drop_node=cr.drop, fare=offer.fare,
        )
        messages.success(request, f'Offer accepted! Driver: {offer.driver.first_name}, Fare: ₹{offer.fare}')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('passenger_dashboard')


@login_required
def cancel_request_page(request, cr_id):
    if request.method != 'POST' or request.user.role != 'passenger':
        return redirect('passenger_dashboard')
    try:
        cr = CarPoolRequest.objects.get(pk=cr_id, passenger=request.user)
        if cr.status == 'matched':
            messages.error(request, 'Cannot cancel a matched request')
        elif cr.status == 'cancelled':
            messages.error(request, 'Already cancelled')
        else:
            cr.status = CarPoolRequest.Status.CANCELLED
            cr.save()
            messages.success(request, 'Carpool request cancelled')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('passenger_dashboard')


@login_required
def toggle_service_page(request):
    if request.method != 'POST' or request.user.role != 'admin':
        return redirect('admin_dashboard')
    from core.models import ServiceConfig
    config, _ = ServiceConfig.objects.get_or_create(pk=1)
    config.is_active = not config.is_active
    config.save()
    state = "activated" if config.is_active else "suspended"
    messages.success(request, f'Service {state}')
    return redirect('admin_dashboard')