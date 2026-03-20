from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from core.models import Node, Edge, ServiceConfig
from .models import Trip, TripNode, TripPassenger, CarPoolRequest, DriverOffer, Transaction
from decimal import Decimal

User = get_user_model()


class TripTestSetup(APITestCase):
    """
    Sets up the graph from seed_test_data and creates users with tokens.

    Graph:
        A → B → C → D → E → F
                ↓   ↓   ↑
                G → H → I
        Also D → I shortcut
    """

    def setUp(self):
        self.nodes = {}
        for name in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']:
            self.nodes[name] = Node.objects.create(name=name, address=f'{name} Address')

        edges = [
            ('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'E'), ('E', 'F'),
            ('C', 'G'), ('G', 'H'), ('H', 'I'), ('I', 'E'), ('D', 'I'),
        ]
        for src, dst in edges:
            Edge.objects.create(source=self.nodes[src], destination=self.nodes[dst], distance=1.0)

        self.admin = User.objects.create_user(
            email='admin@test.com', password='test123',
            first_name='Admin', last_name='User', role='admin', phone_number='1111111111',
        )
        self.driver = User.objects.create_user(
            email='driver@test.com', password='test123',
            first_name='Driver', last_name='Driver', role='driver', phone_number='2222222222',
        )
        self.passenger1 = User.objects.create_user(
            email='passenger1@test.com', password='test123',
            first_name='Passenger', last_name='1', role='passenger', phone_number='3333333333',
        )
        self.passenger2 = User.objects.create_user(
            email='passenger2@test.com', password='test123',
            first_name='Passenger', last_name='2', role='passenger', phone_number='4444444444',
        )

        self.admin_token = self._login('admin@test.com')
        self.driver_token = self._login('driver@test.com')
        self.p1_token = self._login('passenger1@test.com')
        self.p2_token = self._login('passenger2@test.com')
        self.client.logout()

    def _login(self, email):
        resp = self.client.post('/users/api/login/', {'email': email, 'password': 'test123'})
        return resp.data['token']

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

    def n(self, name):
        return self.nodes[name]


# ─── Trip Lifecycle ────────────────────────────────────────────────

class CreateTripTest(TripTestSetup):

    def test_driver_creates_trip(self):
        self.auth(self.driver_token)
        resp = self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        trip = Trip.objects.first()
        self.assertEqual(trip.driver, self.driver)
        route = [tn.node.name for tn in TripNode.objects.filter(trip=trip).order_by('order')]
        self.assertEqual(route, ['A', 'B', 'C', 'D', 'E', 'F'])

    def test_passenger_cannot_create_trip(self):
        self.auth(self.p1_token)
        resp = self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 2,
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_path_returns_400(self):
        self.auth(self.driver_token)
        resp = self.client.post('/trips/api/create/', {
            'start_node': self.n('F').pk, 'end_node': self.n('A').pk, 'max_passengers': 2,
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class StartTripTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        self.trip = Trip.objects.first()

    def test_start_trip(self):
        self.auth(self.driver_token)
        resp = self.client.post(f'/trips/api/{self.trip.pk}/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, 'active')
        self.assertEqual(self.trip.current_node, self.n('A'))

    def test_start_already_active_trip(self):
        self.auth(self.driver_token)
        self.client.post(f'/trips/api/{self.trip.pk}/start/')
        resp = self.client.post(f'/trips/api/{self.trip.pk}/start/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_trip(self):
        self.auth(self.driver_token)
        resp = self.client.post('/trips/api/999/start/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class AdvanceTripTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('D').pk, 'max_passengers': 2,
        })
        self.trip = Trip.objects.first()
        self.client.post(f'/trips/api/{self.trip.pk}/start/')

    def test_advance_moves_to_next_node(self):
        self.auth(self.driver_token)
        resp = self.client.post(f'/trips/api/{self.trip.pk}/advance/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.current_node, self.n('B'))

    def test_advance_to_end_completes_trip(self):
        self.auth(self.driver_token)
        for _ in range(3):  # A→B→C→D
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.current_node, self.n('D'))
        resp = self.client.post(f'/trips/api/{self.trip.pk}/advance/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, 'completed')

    def test_passenger_cannot_advance(self):
        self.auth(self.p1_token)
        resp = self.client.post(f'/trips/api/{self.trip.pk}/advance/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CancelTripTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('D').pk, 'max_passengers': 2,
        })
        self.trip = Trip.objects.first()

    def test_cancel_planned_trip(self):
        self.auth(self.driver_token)
        resp = self.client.post(f'/trips/api/{self.trip.pk}/cancel/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, 'cancelled')

    def test_cancel_active_trip_fails(self):
        self.auth(self.driver_token)
        self.client.post(f'/trips/api/{self.trip.pk}/start/')
        resp = self.client.post(f'/trips/api/{self.trip.pk}/cancel/')
        self.assertNotEqual(resp.status_code, status.HTTP_200_OK)


class FetchDriverTripsTest(TripTestSetup):

    def test_driver_sees_own_trips(self):
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('D').pk, 'max_passengers': 2,
        })
        resp = self.client.get('/trips/api/mine/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_driver_with_no_trips(self):
        self.auth(self.driver_token)
        resp = self.client.get('/trips/api/mine/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class TripDashboardTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        self.trip = Trip.objects.first()

    def test_dashboard_returns_route_info(self):
        self.auth(self.driver_token)
        resp = self.client.get(f'/trips/api/{self.trip.pk}/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['trip_id'], self.trip.pk)
        self.assertEqual(len(resp.data['route']), 6)

    def test_other_driver_cannot_view(self):
        driver2 = User.objects.create_user(
            email='d2@test.com', password='test123',
            first_name='Other', last_name='Driver', role='driver', phone_number='5555555555',
        )
        t = self._login('d2@test.com')
        self.auth(t)
        resp = self.client.get(f'/trips/api/{self.trip.pk}/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ─── Wallet ────────────────────────────────────────────────────────

class WalletTest(TripTestSetup):

    def test_topup(self):
        self.auth(self.p1_token)
        resp = self.client.post('/trips/api/wallet/topup/', {'amount': 100})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.passenger1.refresh_from_db()
        self.assertEqual(self.passenger1.wallet_balance, Decimal('100.00'))
        self.assertEqual(Transaction.objects.filter(user=self.passenger1, type='top_up').count(), 1)

    def test_topup_negative_fails(self):
        self.auth(self.p1_token)
        resp = self.client.post('/trips/api/wallet/topup/', {'amount': -50})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_topup_missing_amount_fails(self):
        self.auth(self.p1_token)
        resp = self.client.post('/trips/api/wallet/topup/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_view_transactions(self):
        self.auth(self.p1_token)
        self.client.post('/trips/api/wallet/topup/', {'amount': 200})
        resp = self.client.get('/trips/api/wallet/transactions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['transactions']), 1)
        self.assertEqual(resp.data['balance'], Decimal('200.00'))

    def test_driver_cannot_topup(self):
        self.auth(self.driver_token)
        resp = self.client.post('/trips/api/wallet/topup/', {'amount': 100})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ─── Carpool Request Flow ─────────────────────────────────────────

class CarpoolRequestTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        self.trip = Trip.objects.first()
        self.client.post(f'/trips/api/{self.trip.pk}/start/')

    def test_passenger_creates_request(self):
        self.auth(self.p1_token)
        resp = self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('G').pk, 'drop': self.n('I').pk,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CarPoolRequest.objects.count(), 1)

    def test_driver_cannot_create_request(self):
        self.auth(self.driver_token)
        resp = self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('B').pk, 'drop': self.n('D').pk,
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_sees_matching_requests(self):
        self.auth(self.p1_token)
        self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('G').pk, 'drop': self.n('I').pk,
        })
        self.auth(self.driver_token)
        resp = self.client.get('/trips/api/carpool/requests/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)

    def test_cancel_pending_request(self):
        self.auth(self.p1_token)
        self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('B').pk, 'drop': self.n('D').pk,
        })
        cr = CarPoolRequest.objects.first()
        resp = self.client.post(f'/trips/api/carpool/request/{cr.pk}/cancel/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cr.refresh_from_db()
        self.assertEqual(cr.status, 'cancelled')

    def test_cancel_already_cancelled_fails(self):
        self.auth(self.p1_token)
        self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('B').pk, 'drop': self.n('D').pk,
        })
        cr = CarPoolRequest.objects.first()
        self.client.post(f'/trips/api/carpool/request/{cr.pk}/cancel/')
        resp = self.client.post(f'/trips/api/carpool/request/{cr.pk}/cancel/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ─── Driver Offer + Passenger Accept ──────────────────────────────

class OfferAcceptFlowTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.passenger1.wallet_balance = Decimal('500')
        self.passenger1.save()

        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        self.trip = Trip.objects.first()
        self.client.post(f'/trips/api/{self.trip.pk}/start/')

        self.auth(self.p1_token)
        self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('B').pk, 'drop': self.n('D').pk,
        })
        self.cr = CarPoolRequest.objects.first()

    def test_driver_creates_offer(self):
        self.auth(self.driver_token)
        resp = self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('fare', resp.data)
        self.assertIn('detour', resp.data)

    def test_duplicate_offer_rejected(self):
        self.auth(self.driver_token)
        self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        resp = self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_passenger_views_offers(self):
        self.auth(self.driver_token)
        self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        self.auth(self.p1_token)
        resp = self.client.get(f'/trips/api/carpool/request/{self.cr.pk}/offers/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_no_offers_yet(self):
        self.auth(self.p1_token)
        resp = self.client.get(f'/trips/api/carpool/request/{self.cr.pk}/offers/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('message', resp.data)

    def test_accept_offer(self):
        self.auth(self.driver_token)
        self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        offer = DriverOffer.objects.first()

        self.auth(self.p1_token)
        resp = self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/accept/{offer.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        offer.refresh_from_db()
        self.assertEqual(offer.status, 'accepted')
        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, 'matched')
        self.assertEqual(TripPassenger.objects.filter(trip=self.trip, passenger=self.passenger1).count(), 1)

    def test_accept_with_insufficient_balance_fails(self):
        self.passenger1.wallet_balance = Decimal('0')
        self.passenger1.save()

        self.auth(self.driver_token)
        self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        offer = DriverOffer.objects.first()

        self.auth(self.p1_token)
        resp = self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/accept/{offer.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_matched_request_fails(self):
        self.auth(self.driver_token)
        self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        offer = DriverOffer.objects.first()
        self.auth(self.p1_token)
        self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/accept/{offer.pk}/')
        resp = self.client.post(f'/trips/api/carpool/request/{self.cr.pk}/cancel/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ─── Board & Drop-off ─────────────────────────────────────────────

class BoardDropoffTest(TripTestSetup):

    def setUp(self):
        super().setUp()
        self.passenger1.wallet_balance = Decimal('500')
        self.passenger1.save()

        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        self.trip = Trip.objects.first()
        self.client.post(f'/trips/api/{self.trip.pk}/start/')

        self.auth(self.p1_token)
        self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('B').pk, 'drop': self.n('D').pk,
        })
        cr = CarPoolRequest.objects.first()

        self.auth(self.driver_token)
        self.client.post(f'/trips/api/carpool/request/{cr.pk}/offer/', {
            'trip_id': self.trip.pk,
        })
        offer = DriverOffer.objects.first()

        self.auth(self.p1_token)
        self.client.post(f'/trips/api/carpool/request/{cr.pk}/accept/{offer.pk}/')

        self.tp = TripPassenger.objects.get(trip=self.trip, passenger=self.passenger1)

    def test_board_at_wrong_node_fails(self):
        self.auth(self.driver_token)
        resp = self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_board_at_correct_node(self):
        self.auth(self.driver_token)
        self.trip.refresh_from_db()
        while self.trip.current_node != self.tp.pickup:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()

        resp = self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.tp.refresh_from_db()
        self.assertEqual(self.tp.boarding_status, 'boarded')

    def test_board_already_boarded_fails(self):
        self.auth(self.driver_token)
        self.trip.refresh_from_db()
        while self.trip.current_node != self.tp.pickup:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()
        self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')
        resp = self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dropoff_deducts_fare_and_credits_driver(self):
        self.auth(self.driver_token)
        self.trip.refresh_from_db()

        while self.trip.current_node != self.tp.pickup:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()
        self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')

        while self.trip.current_node != self.tp.drop:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()

        balance_before = self.passenger1.wallet_balance
        driver_balance_before = self.driver.wallet_balance
        resp = self.client.post(f'/trips/api/{self.trip.pk}/dropoff/{self.passenger1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.passenger1.refresh_from_db()
        self.driver.refresh_from_db()
        self.tp.refresh_from_db()

        self.assertEqual(self.tp.boarding_status, 'dropped')
        self.assertLess(self.passenger1.wallet_balance, balance_before)
        self.assertGreater(self.driver.wallet_balance, driver_balance_before)
        self.assertTrue(Transaction.objects.filter(user=self.passenger1, type='fare_deduction').exists())
        self.assertTrue(Transaction.objects.filter(user=self.driver, type='driver_earning').exists())

    def test_dropoff_at_wrong_node_fails(self):
        self.auth(self.driver_token)
        self.trip.refresh_from_db()
        while self.trip.current_node != self.tp.pickup:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()
        self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')
        resp = self.client.post(f'/trips/api/{self.trip.pk}/dropoff/{self.passenger1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dropoff_insufficient_balance_fails(self):
        self.auth(self.driver_token)
        self.trip.refresh_from_db()
        while self.trip.current_node != self.tp.pickup:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()
        self.client.post(f'/trips/api/{self.trip.pk}/board/{self.passenger1.pk}/')

        self.passenger1.wallet_balance = Decimal('0')
        self.passenger1.save()

        while self.trip.current_node != self.tp.drop:
            self.client.post(f'/trips/api/{self.trip.pk}/advance/')
            self.trip.refresh_from_db()

        resp = self.client.post(f'/trips/api/{self.trip.pk}/dropoff/{self.passenger1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ─── Admin Endpoints ──────────────────────────────────────────────

class AdminTest(TripTestSetup):

    def test_admin_views_active_trips(self):
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('D').pk, 'max_passengers': 2,
        })
        trip = Trip.objects.first()
        self.client.post(f'/trips/api/{trip.pk}/start/')

        self.auth(self.admin_token)
        resp = self.client.get('/trips/api/admin/active/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_admin_no_active_trips(self):
        self.auth(self.admin_token)
        resp = self.client.get('/trips/api/admin/active/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('message', resp.data)

    def test_non_admin_cannot_view_active_trips(self):
        self.auth(self.driver_token)
        resp = self.client.get('/trips/api/admin/active/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_toggle_service_suspends(self):
        self.auth(self.admin_token)
        resp = self.client.post('/trips/api/admin/service/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['is_active'])

    def test_toggle_service_reactivates(self):
        ServiceConfig.objects.get_or_create(pk=1, defaults={'is_active': True})
        config = ServiceConfig.objects.get(pk=1)
        config.is_active = False
        config.save()

        self.auth(self.admin_token)
        resp = self.client.post('/trips/api/admin/service/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['is_active'])

    def test_non_admin_cannot_toggle_service(self):
        self.auth(self.p1_token)
        resp = self.client.post('/trips/api/admin/service/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ─── Mid-Ride Carpool (Phase 2) ───────────────────────────────────

class MidRideCarpoolTest(TripTestSetup):

    def test_request_matches_active_trip(self):
        self.auth(self.driver_token)
        self.client.post('/trips/api/create/', {
            'start_node': self.n('A').pk, 'end_node': self.n('F').pk, 'max_passengers': 3,
        })
        trip = Trip.objects.first()
        self.client.post(f'/trips/api/{trip.pk}/start/')
        self.client.post(f'/trips/api/{trip.pk}/advance/')  # A→B

        self.auth(self.p1_token)
        self.client.post('/trips/api/carpool/request/', {
            'pickup': self.n('C').pk, 'drop': self.n('E').pk,
        })

        self.auth(self.driver_token)
        resp = self.client.get('/trips/api/carpool/requests/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)
