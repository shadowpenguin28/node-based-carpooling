from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import Node, Edge

User = get_user_model()


class NodeViewTestSetup(APITestCase):
    """Base setup for Node tests — creates an admin and a passenger user."""

    def setUp(self):
        # Admin user (note: role must match what IsAdmin permission checks)
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            role='admin',
            phone_number='1234567890',
            first_name='Admin',
            last_name='User',
        )
        # Non-admin user
        self.passenger = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            role='passenger',
            phone_number='0987654321',
            first_name='Passenger',
            last_name='User',
        )
        # Login admin and get token
        response = self.client.post('/users/login/', {
            'email': 'admin@test.com',
            'password': 'testpass123',
        })
        self.admin_token = response.data['token']

        # Login passenger and get token
        response = self.client.post('/users/login/', {
            'email': 'passenger@test.com',
            'password': 'testpass123',
        })
        self.passenger_token = response.data['token']

    def auth_as_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.admin_token)

    def auth_as_passenger(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.passenger_token)


# ─── Node CRUD Tests ───────────────────────────────────────────────

class CreateNodeTest(NodeViewTestSetup):

    def test_admin_can_create_node(self):
        self.auth_as_admin()
        data = {'name': 'Node A', 'address': '123 Main St'}
        response = self.client.post('/core/nodes/create/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Node.objects.count(), 1)
        self.assertEqual(Node.objects.first().name, 'Node A')

    def test_passenger_cannot_create_node(self):
        self.auth_as_passenger()
        data = {'name': 'Node A', 'address': '123 Main St'}
        response = self.client.post('/core/nodes/create/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_node(self):
        data = {'name': 'Node A', 'address': '123 Main St'}
        response = self.client.post('/core/nodes/create/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_node_missing_fields(self):
        self.auth_as_admin()
        data = {'name': 'Node A'}  # missing address
        response = self.client.post('/core/nodes/create/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RetrieveNodeTest(NodeViewTestSetup):

    def setUp(self):
        super().setUp()
        self.node = Node.objects.create(name='Node A', address='123 Main St')

    def test_authenticated_can_retrieve_node(self):
        self.auth_as_passenger()
        response = self.client.get(f'/core/nodes/{self.node.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Node A')

    def test_unauthenticated_cannot_retrieve_node(self):
        response = self.client.get(f'/core/nodes/{self.node.pk}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_nonexistent_node(self):
        self.auth_as_passenger()
        response = self.client.get('/core/nodes/999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UpdateNodeTest(NodeViewTestSetup):

    def setUp(self):
        super().setUp()
        self.node = Node.objects.create(name='Node A', address='123 Main St')

    def test_admin_can_update_node(self):
        self.auth_as_admin()
        data = {'name': 'Node A Updated', 'address': '456 New St'}
        response = self.client.put(f'/core/nodes/{self.node.pk}/update/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.node.refresh_from_db()
        self.assertEqual(self.node.name, 'Node A Updated')

    def test_passenger_cannot_update_node(self):
        self.auth_as_passenger()
        data = {'name': 'Hacked', 'address': 'Hacked'}
        response = self.client.put(f'/core/nodes/{self.node.pk}/update/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_nonexistent_node(self):
        self.auth_as_admin()
        data = {'name': 'Ghost', 'address': 'Nowhere'}
        response = self.client.put('/core/nodes/999/update/', data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DeleteNodeTest(NodeViewTestSetup):

    def setUp(self):
        super().setUp()
        self.node = Node.objects.create(name='Node A', address='123 Main St')

    def test_admin_can_delete_node(self):
        self.auth_as_admin()
        response = self.client.delete(f'/core/nodes/{self.node.pk}/delete/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Node.objects.count(), 0)

    def test_passenger_cannot_delete_node(self):
        self.auth_as_passenger()
        response = self.client.delete(f'/core/nodes/{self.node.pk}/delete/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_nonexistent_node(self):
        self.auth_as_admin()
        response = self.client.delete('/core/nodes/999/delete/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ─── Edge CRUD Tests ───────────────────────────────────────────────

class EdgeViewTestSetup(NodeViewTestSetup):
    """Extends NodeViewTestSetup with two nodes for edge tests."""

    def setUp(self):
        super().setUp()
        self.node_a = Node.objects.create(name='Node A', address='Address A')
        self.node_b = Node.objects.create(name='Node B', address='Address B')


class CreateEdgeTest(EdgeViewTestSetup):

    def test_admin_can_create_edge(self):
        self.auth_as_admin()
        data = {'source': self.node_a.pk, 'destination': self.node_b.pk, 'distance': 5.0}
        response = self.client.post('/core/edges/create/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Edge.objects.count(), 1)

    def test_passenger_cannot_create_edge(self):
        self.auth_as_passenger()
        data = {'source': self.node_a.pk, 'destination': self.node_b.pk, 'distance': 5.0}
        response = self.client.post('/core/edges/create/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_edge_rejected(self):
        self.auth_as_admin()
        data = {'source': self.node_a.pk, 'destination': self.node_b.pk, 'distance': 5.0}
        self.client.post('/core/edges/create/', data)  # first one
        response = self.client.post('/core/edges/create/', data)  # duplicate
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reverse_edge_allowed(self):
        self.auth_as_admin()
        # A → B
        self.client.post('/core/edges/create/', {
            'source': self.node_a.pk, 'destination': self.node_b.pk, 'distance': 5.0
        })
        # B → A (reverse direction, should be allowed)
        response = self.client.post('/core/edges/create/', {
            'source': self.node_b.pk, 'destination': self.node_a.pk, 'distance': 3.0
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Edge.objects.count(), 2)


class RetrieveEdgeTest(EdgeViewTestSetup):

    def setUp(self):
        super().setUp()
        self.edge = Edge.objects.create(source=self.node_a, destination=self.node_b, distance=5.0)

    def test_authenticated_can_retrieve_edge(self):
        self.auth_as_passenger()
        response = self.client.get(f'/core/edges/{self.edge.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['distance'], 5.0)

    def test_retrieve_nonexistent_edge(self):
        self.auth_as_passenger()
        response = self.client.get('/core/edges/999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UpdateEdgeTest(EdgeViewTestSetup):

    def setUp(self):
        super().setUp()
        self.edge = Edge.objects.create(source=self.node_a, destination=self.node_b, distance=5.0)

    def test_admin_can_update_edge(self):
        self.auth_as_admin()
        data = {'source': self.node_a.pk, 'destination': self.node_b.pk, 'distance': 10.0}
        response = self.client.put(f'/core/edges/{self.edge.pk}/update/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.edge.refresh_from_db()
        self.assertEqual(self.edge.distance, 10.0)

    def test_passenger_cannot_update_edge(self):
        self.auth_as_passenger()
        data = {'source': self.node_a.pk, 'destination': self.node_b.pk, 'distance': 10.0}
        response = self.client.put(f'/core/edges/{self.edge.pk}/update/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DeleteEdgeTest(EdgeViewTestSetup):

    def setUp(self):
        super().setUp()
        self.edge = Edge.objects.create(source=self.node_a, destination=self.node_b, distance=5.0)

    def test_admin_can_delete_edge(self):
        self.auth_as_admin()
        response = self.client.delete(f'/core/edges/{self.edge.pk}/delete/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Edge.objects.count(), 0)

    def test_passenger_cannot_delete_edge(self):
        self.auth_as_passenger()
        response = self.client.delete(f'/core/edges/{self.edge.pk}/delete/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_node_cascades_edges(self):
        """Deleting a node should also delete its connected edges."""
        self.assertEqual(Edge.objects.count(), 1)
        self.node_a.delete()
        self.assertEqual(Edge.objects.count(), 0)
