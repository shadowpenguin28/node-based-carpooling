"""
Seed command: creates a test graph, users, and prints curl commands for full E2E test.
Usage: python manage.py seed_test_data
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Node, Edge
from trips.models import Trip, TripNode, TripPassenger, CarPoolRequest, DriverOffer

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds test graph, users, and prints curl commands for E2E testing'

    def handle(self, *args, **options):
        self.stdout.write('\n=== Cleaning existing data ===')
        DriverOffer.objects.all().delete()
        CarPoolRequest.objects.all().delete()
        TripPassenger.objects.all().delete()
        TripNode.objects.all().delete()
        Trip.objects.all().delete()
        Edge.objects.all().delete()
        Node.objects.all().delete()
        User.objects.filter(email__in=[
            'admin@test.com', 'driver1@test.com',
            'passenger1@test.com', 'passenger2@test.com',
        ]).delete()

        self.stdout.write('\n=== Creating Nodes ===')
        # Graph layout:
        #   A → B → C → D → E → F
        #           ↓   ↓   ↑
        #           G → H → I
        #
        # One-way: G→H→I→E (can't go E→I)
        # D→I shortcut so I is within 1 hop of route node D

        nodes = {}
        for name in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']:
            nodes[name] = Node.objects.create(name=name, address=f'{name} Address')
            self.stdout.write(f'  Node {name} (id={nodes[name].id})')

        self.stdout.write('\n=== Creating Edges ===')
        edges = [
            ('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'E'), ('E', 'F'),  # main route
            ('C', 'G'),  # branch off
            ('G', 'H'), ('H', 'I'),  # side route
            ('I', 'E'),  # rejoin main route (one-way: can go I→E, but NOT E→I)
            ('D', 'I'),  # shortcut: I is 1 hop from D
        ]
        for src, dst in edges:
            Edge.objects.create(source=nodes[src], destination=nodes[dst], distance=1.0)
            self.stdout.write(f'  {src} → {dst}')

        self.stdout.write('\n=== Creating Users ===')
        admin = User.objects.create_user(
            email='admin@test.com', password='test123',
            first_name='Admin', last_name='User',
            role='admin', phone_number='1111111111',
        )
        driver = User.objects.create_user(
            email='driver1@test.com', password='test123',
            first_name='Dave', last_name='Driver',
            role='driver', phone_number='2222222222',
        )
        p1 = User.objects.create_user(
            email='passenger1@test.com', password='test123',
            first_name='Alice', last_name='Passenger',
            role='passenger', phone_number='3333333333',
        )
        p2 = User.objects.create_user(
            email='passenger2@test.com', password='test123',
            first_name='Bob', last_name='Passenger',
            role='passenger', phone_number='4444444444',
        )

        self.stdout.write(f'  Admin: admin@test.com (id={admin.id})')
        self.stdout.write(f'  Driver: driver1@test.com (id={driver.id})')
        self.stdout.write(f'  Passenger1: passenger1@test.com (id={p1.id})')
        self.stdout.write(f'  Passenger2: passenger2@test.com (id={p2.id})')

        # Print node IDs for reference
        self.stdout.write('\n=== Node IDs ===')
        for name, node in nodes.items():
            self.stdout.write(f'  {name} = {node.id}')

        g_id = nodes['G'].id
        i_id = nodes['I'].id
        h_id = nodes['H'].id
        a_id = nodes['A'].id
        f_id = nodes['F'].id

        self.stdout.write(self.style.SUCCESS(f'''
==========================================================
  TEST SCRIPT — Run these curl commands in order
==========================================================

# ─── 1. LOGIN ALL USERS ────────────────────────────────

# Login Admin
curl -s -X POST http://localhost:8000/users/login/ \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"admin@test.com","password":"test123"}}'
# → Save the "token" value as ADMIN_TOKEN

# Login Driver
curl -s -X POST http://localhost:8000/users/login/ \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"driver1@test.com","password":"test123"}}'
# → Save the "token" value as DRIVER_TOKEN

# Login Passenger 1
curl -s -X POST http://localhost:8000/users/login/ \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"passenger1@test.com","password":"test123"}}'
# → Save the "token" value as P1_TOKEN

# Login Passenger 2
curl -s -X POST http://localhost:8000/users/login/ \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"passenger2@test.com","password":"test123"}}'
# → Save the "token" value as P2_TOKEN


# ─── 2. DRIVER CREATES TRIP (A → F) ───────────────────

curl -s -X POST http://localhost:8000/trips/create/ \\
  -H "Authorization: Token $DRIVER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"start_node":{a_id},"end_node":{f_id},"max_passengers":3}}'
# → Route: A→B→C→D→E→F. Save trip ID as TRIP_ID


# ─── 3. DRIVER STARTS TRIP ────────────────────────────

curl -s -X POST http://localhost:8000/trips/$TRIP_ID/start/ \\
  -H "Authorization: Token $DRIVER_TOKEN"
# → Trip ACTIVE, current_node = A


# ─── 4. PASSENGER 1 REQUESTS CARPOOL (G → I) ─────────

curl -s -X POST http://localhost:8000/trips/carpool/request/ \\
  -H "Authorization: Token $P1_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"pickup":{g_id},"drop":{i_id}}}'
# → Save request ID as CR1_ID


# ─── 5. PASSENGER 2 REQUESTS CARPOOL (H → I) ─────────

curl -s -X POST http://localhost:8000/trips/carpool/request/ \\
  -H "Authorization: Token $P2_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"pickup":{h_id},"drop":{i_id}}}'
# → Save request ID as CR2_ID


# ─── 6. DRIVER VIEWS MATCHING REQUESTS ────────────────

curl -s -X GET http://localhost:8000/trips/carpool/requests/ \\
  -H "Authorization: Token $DRIVER_TOKEN"
# → Should see both requests (G and H within 2 hops of route)


# ─── 7. DRIVER OFFERS ON BOTH REQUESTS ────────────────

curl -s -X POST http://localhost:8000/trips/carpool/request/$CR1_ID/offer/ \\
  -H "Authorization: Token $DRIVER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"trip_id":$TRIP_ID}}'
# → Save offer ID as OFFER1_ID

curl -s -X POST http://localhost:8000/trips/carpool/request/$CR2_ID/offer/ \\
  -H "Authorization: Token $DRIVER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"trip_id":$TRIP_ID}}'
# → Save offer ID as OFFER2_ID


# ─── 8. PASSENGERS VIEW OFFERS ────────────────────────

curl -s -X GET http://localhost:8000/trips/carpool/request/$CR1_ID/offers/ \\
  -H "Authorization: Token $P1_TOKEN"

curl -s -X GET http://localhost:8000/trips/carpool/request/$CR2_ID/offers/ \\
  -H "Authorization: Token $P2_TOKEN"


# ─── 9. PASSENGERS ACCEPT OFFERS ──────────────────────

curl -s -X POST http://localhost:8000/trips/carpool/request/$CR1_ID/accept/$OFFER1_ID/ \\
  -H "Authorization: Token $P1_TOKEN"

curl -s -X POST http://localhost:8000/trips/carpool/request/$CR2_ID/accept/$OFFER2_ID/ \\
  -H "Authorization: Token $P2_TOKEN"


# ─── 10. DRIVER VIEWS TRIP DASHBOARD ──────────────────

curl -s -X GET http://localhost:8000/trips/$TRIP_ID/dashboard/ \\
  -H "Authorization: Token $DRIVER_TOKEN"
# → Shows route, both passengers, accepted offers


# ─── 11. DRIVER ADVANCES THROUGH ROUTE ────────────────

curl -s -X POST http://localhost:8000/trips/$TRIP_ID/advance/ \\
  -H "Authorization: Token $DRIVER_TOKEN"
# Repeat to move A→B→C→D→E→F


# ─── 12. ADMIN VIEWS ACTIVE TRIPS ─────────────────────

curl -s -X GET http://localhost:8000/trips/admin/active/ \\
  -H "Authorization: Token $ADMIN_TOKEN"


# ─── 13. ADMIN TOGGLES SERVICE OFF ────────────────────

curl -s -X POST http://localhost:8000/trips/admin/service/toggle/ \\
  -H "Authorization: Token $ADMIN_TOKEN"
# → Service suspended

# Should get 503:
curl -s -X GET http://localhost:8000/trips/mine/ \\
  -H "Authorization: Token $DRIVER_TOKEN"

# Toggle back on:
curl -s -X POST http://localhost:8000/trips/admin/service/toggle/ \\
  -H "Authorization: Token $ADMIN_TOKEN"
'''))
