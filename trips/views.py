from django.shortcuts import render
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsDriver, IsPassenger, IsAdmin
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model, authenticate

from .serializers import TripCreateSerializer, CarPoolRequestSerializer
from . import services
from .models import Trip, TripPassenger, TripNode, CarPoolRequest, DriverOffer
# Create your views here.

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def create_trip_view(request):
    serializer = TripCreateSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(data={"errors": "Invalid data"}, status=status.HTTP_400_BAD_REQUEST)
        
    data = serializer.validated_data
    trip = services.create_trip(
        driver = request.user,
        start_node=data['start_node'],
        end_node = data['end_node'],
        max_passengers=data['max_passengers']
    )
    if trip is None:
        return Response(data={"error": "Trip could not be created"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(data={"message": "success"}, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def start_trip_view(request, trip_id):
    try:
        trip = Trip.objects.get(pk = trip_id)
    except:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if trip.status != Trip.Status.PLANNED:
        return Response(data={"errors": "Trip cannot be started"})
    if request.user != trip.driver:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)
    
    # trip.status == PLANNED
    trip.start_trip()

    return Response(data={"message": "Trip successfully started"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def advance_trip_view(request, trip_id):
    try:
        trip = Trip.objects.get(pk = trip_id)
    except:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user != trip.driver:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    next_node = trip.advance_to_next_node()

    if next_node:
        return Response(data={"message": "Advanced to next node"}, status=status.HTTP_200_OK)
    
    # next_node is None i.e. current_node is end_node and trying to advance

    return Response(data={"message": "Trip completed!"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDriver])
def cancel_trip_view(request, trip_id):
    try:
        trip = Trip.objects.get(pk = trip_id)
    except:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)
    
    if request.user != trip.driver:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    if trip.status != Trip.Status.PLANNED:
        return Response(data={"message": "Trip cannot be cancelled!"}, status=status.HTTP_304_NOT_MODIFIED)

    trip.cancel_trip()
    return Response(data={"message": "Cancelled!"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPassenger])
def create_carpool_request(request):
    serializer = CarPoolRequestSerializer(data=request.data)

    if serializer.is_valid():
        data = serializer.validated_data
        CarPoolRequest.objects.create(
            passenger = request.user,
            pickup = data['pickup'],
            drop = data['drop']
        )

        return Response(data={"message": "Carpool request created"}, status=status.HTTP_201_CREATED)
    return Response(data={'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPassenger])
def view_driver_offers(request, cr_id):  #cr_id => carpool request id
    try:
        cr_req = CarPoolRequest.objects.get(pk=cr_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors": "Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.user != cr_req.passenger:
        return Response(data={"errors": "Not your Carpool Request"}, status=status.HTTP_403_FORBIDDEN)

    offers = DriverOffer.objects.filter(carpool_request_id = cr_id)

    response_data = {}
    if offers.exists():
        for offer in offers:
            response_data[offer.id] = {
                'driver': f"{offer.driver.first_name} {offer.driver.last_name}",
                'trip': offer.trip.id,
                'fare': offer.fare,
                'detour': offer.detour,
                'status': offer.status
            }
        return Response(data=response_data, status=status.HTTP_200_OK)
    
    return Response(data={"message": "No offers yet"}, status=status.HTTP_200_OK)

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
    
    # Accept the offer
    offer.status = DriverOffer.Status.ACCEPTED
    offer.save()

    # Mark carpool request as matched
    req.status = CarPoolRequest.Status.MATCHED
    req.save()

    # Reject all other pending offers for this request
    DriverOffer.objects.filter(
        carpool_request=req, status='pending'
    ).exclude(pk=offer.pk).update(status='rejected')

    # Add passenger to the trip
    services.add_passenger_to_trip(
        passenger=req.passenger,
        trip=offer.trip,
        pickup_node=req.pickup,
        drop_node=req.drop,
    )

    return Response(data={
        "message": "Accepted offer!",
        "driver": f"{offer.driver.first_name} {offer.driver.last_name}",
        "detour": offer.detour,
        "fare": offer.fare, 
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPassenger])
def cancel_carpool_request(request, cr_id): #cr_id => carpool request id
    try:
        req = CarPoolRequest.objects.get(pk=cr_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors":"Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if req.passenger != request.user:
        return Response(data={"errors": "Not your carpool request"}, status=status.HTTP_403_FORBIDDEN)

    # check if the carpool request is not accepted by a driver
    if req.status == CarPoolRequest.Status.MATCHED:
        return Response(data={"errors": "Cannot cancel this carpool request, already matched!"}, status=status.HTTP_400_BAD_REQUEST)
    if req.status == CarPoolRequest.Status.CANCELLED:
        return Response(data={"errors": "Carpool request is already cancelled!"}, status=status.HTTP_400_BAD_REQUEST)

    # PENDING request
    req.status = CarPoolRequest.Status.CANCELLED
    req.save()

    return Response(data={"messages": "Cancelled carpool request"}, status=status.HTTP_200_OK) 
 
# ─── Driver-facing carpool endpoints ───────────────────────────────

PRICE_PER_HOP = 10  # configurable
BASE_FEE = 5

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDriver])
def view_carpool_requests(request):
    """Driver sees all pending carpool requests that match their active trips."""
    driver_trips = Trip.objects.filter(driver=request.user, status__in=['planned', 'active'])
    
    if not driver_trips.exists():
        return Response(data={"message": "No active trips"}, status=status.HTTP_200_OK)
    
    pending_requests = CarPoolRequest.objects.filter(status='pending')
    matching = []

    for cr in pending_requests:
        matched_trips = services.find_matching_trips(cr.pickup, cr.drop)
        # Only show requests that match THIS driver's trips
        for trip in matched_trips:
            if trip.driver == request.user:
                detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
                if detour_info:
                    passenger_hops = len(detour_info['path_pickup_to_drop']) - 1
                    n_existing = trip.active_passenger_count + 1
                    fare = PRICE_PER_HOP * passenger_hops / n_existing + BASE_FEE
                    fare = round(fare, 2)
                else:
                    fare = None
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
    """Driver offers to take a passenger for a specific carpool request."""
    try:
        cr = CarPoolRequest.objects.get(pk=req_id)
    except CarPoolRequest.DoesNotExist:
        return Response(data={"errors": "Carpool request not found"}, status=status.HTTP_404_NOT_FOUND)

    if cr.status != CarPoolRequest.Status.PENDING:
        return Response(data={"errors": "Request is no longer pending"}, status=status.HTTP_400_BAD_REQUEST)

    # Find which of this driver's trips matches
    trip_id = request.data.get('trip_id')
    if not trip_id:
        return Response(data={"errors": "trip_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        trip = Trip.objects.get(pk=trip_id, driver=request.user)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found or not yours"}, status=status.HTTP_404_NOT_FOUND)

    # Check if driver already offered for this request
    if DriverOffer.objects.filter(carpool_request=cr, driver=request.user).exists():
        return Response(data={"errors": "You already offered for this request"}, status=status.HTTP_400_BAD_REQUEST)

    # Calculate detour and fare
    detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
    if detour_info is None:
        return Response(data={"errors": "Cannot reach pickup/drop from your route"}, status=status.HTTP_400_BAD_REQUEST)

    passenger_hops = len(detour_info['path_pickup_to_drop']) - 1
    n_existing = trip.active_passenger_count + 1
    fare = round(PRICE_PER_HOP * passenger_hops / n_existing + BASE_FEE, 2)

    # Create the offer
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
        return Response(data={"message": "No active/past trips"}, status=status.HTTP_404_NOT_FOUND)
    trips = []
    for trip in qs:
        trips.append(
            {
                'id': trip.id,
                'status': trip.status,
                'start_node': trip.start_node.name,
                'end_node': trip.end_node.name,
                'current_node': trip.current_node.name if trip.current_node else None,
                'passenger_count': trip.active_passenger_count,
                'max_passengers': trip.max_passengers,
                'created_at': trip.created_at
            }
        ) 
    
    return Response(data=trips, status=status.HTTP_200_OK)

# Admin api end points
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_view_active_trips(request):
    qs = Trip.objects.filter(status="active")
    if not qs.exists():
        return Response(data={"message": "No active trips"})
    
    trips = []
    for trip in qs:
        trips.append(
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
                'created_at': trip.created_at
            }
        ) 
    
    return Response(data=trips, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDriver])
def trip_dashboard(request, trip_id):
    """Driver's detailed view of a specific trip: route, passengers, pending offers."""
    try:
        trip = Trip.objects.get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response(data={"errors": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

    if trip.driver != request.user:
        return Response(data={"errors": "Not your trip"}, status=status.HTTP_403_FORBIDDEN)

    # Route
    route = [
        {'order': tn.order, 'node': tn.node.name, 'node_id': tn.node.id}
        for tn in TripNode.objects.filter(trip=trip).order_by('order')
    ]

    # Passengers
    passengers = []
    for tp in TripPassenger.objects.filter(trip=trip):
        passengers.append({
            'name': f"{tp.passenger.first_name} {tp.passenger.last_name}",
            'boarding_status': tp.boarding_status,
            'pickup': tp.pickup.name,
            'drop': tp.drop.name,
            'fare': tp.fare,
        })

    # Pending offers this driver has made
    pending_offers = []
    for offer in DriverOffer.objects.filter(trip=trip, driver=request.user):
        pending_offers.append({
            'offer_id': offer.id,
            'passenger': f"{offer.carpool_request.passenger.first_name} {offer.carpool_request.passenger.last_name}",
            'pickup': offer.carpool_request.pickup.name,
            'drop': offer.carpool_request.drop.name,
            'fare': offer.fare,
            'detour': offer.detour,
            'status': offer.status,
        })

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
        'offers': pending_offers,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_toggle_service(request):
    """Admin can suspend or re-enable the carpooling service."""
    from core.models import ServiceConfig
    config, _ = ServiceConfig.objects.get_or_create(pk=1)
    config.is_active = not config.is_active
    config.save()

    state = "active" if config.is_active else "suspended"
    return Response(data={"message": f"Carpooling service is now {state}", "is_active": config.is_active}, status=status.HTTP_200_OK)


# ─── SSR Page ──────────────────────────────────────────────────────

from django.contrib.auth.decorators import login_required

@login_required
def driver_dashboard_page(request):
    """Server-side rendered driver dashboard page."""
    if request.user.role != 'driver':
        return render(request, 'trips/driver_dashboard.html', {'error': 'Only drivers can access this page'})

    driver_trips = Trip.objects.filter(driver=request.user).order_by('-created_at')

    trips_data = []
    for trip in driver_trips:
        # Route with current position markers
        route_nodes = TripNode.objects.filter(trip=trip).order_by('order')
        current_order = None
        if trip.current_node:
            try:
                current_tn = TripNode.objects.get(trip=trip, node=trip.current_node)
                current_order = current_tn.order
            except TripNode.DoesNotExist:
                pass

        route = []
        for tn in route_nodes:
            route.append({
                'order': tn.order,
                'name': tn.node.name,
                'is_current': current_order is not None and tn.order == current_order,
                'is_passed': current_order is not None and tn.order < current_order,
            })

        # Passengers
        passengers = []
        for tp in TripPassenger.objects.filter(trip=trip):
            passengers.append({
                'name': f"{tp.passenger.first_name} {tp.passenger.last_name}",
                'boarding_status': tp.boarding_status,
                'pickup': tp.pickup.name,
                'drop': tp.drop.name,
                'fare': tp.fare,
            })

        # Offers
        offers = []
        for offer in DriverOffer.objects.filter(trip=trip, driver=request.user):
            offers.append({
                'passenger': f"{offer.carpool_request.passenger.first_name} {offer.carpool_request.passenger.last_name}",
                'pickup': offer.carpool_request.pickup.name,
                'drop': offer.carpool_request.drop.name,
                'fare': offer.fare,
                'detour': offer.detour,
                'status': offer.status,
            })

        # Matching carpool requests
        matching_requests = []
        if trip.status in ['planned', 'active'] and trip.can_board_more:
            pending_requests = CarPoolRequest.objects.filter(status='pending')
            for cr in pending_requests:
                matched = services.find_matching_trips(cr.pickup, cr.drop)
                if trip in matched:
                    detour_info = services.calculate_detour(trip, cr.pickup, cr.drop)
                    fare = services.calculate_fare(trip, cr.pickup, cr.drop, PRICE_PER_HOP, BASE_FEE)
                    matching_requests.append({
                        'request_id': cr.id,
                        'passenger': f"{cr.passenger.first_name} {cr.passenger.last_name}",
                        'pickup': cr.pickup.name,
                        'drop': cr.drop.name,
                        'detour': detour_info['detour'] if detour_info else '?',
                        'fare': fare if fare else '?',
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

    return render(request, 'trips/driver_dashboard.html', {
        'driver_name': f"{request.user.first_name} {request.user.last_name}",
        'trips': trips_data,
    })

@login_required
def passenger_dashboard_page(request):
    if request.user.role != 'passenger':
        return render(request, 'trips/passenger_dashboard.html', {'error': 'Only passengers can access this page'})
    
    carpool_requests = CarPoolRequest.objects.filter(passenger=request.user).order_by('-created_at')
    
    return render(request, 'trips/passenger_dashboard.html', {
        'passenger_name': f"{request.user.first_name} {request.user.last_name}",
        'carpool_requests': carpool_requests,
    })

@login_required
def admin_dashboard_page(request):
    if request.user.role != 'admin':
        return render(request, 'trips/admin_dashboard.html', {'error': 'Only admins can access this page'})
    
    active_trips = Trip.objects.filter(status='active').order_by('-created_at')
    
    return render(request, 'trips/admin_dashboard.html', {
        'admin_name': f"{request.user.first_name} {request.user.last_name}",
        'active_trips': active_trips,
    })
