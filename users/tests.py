from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from faker import Faker
# Create your tests here.
User = get_user_model()
f = Faker()
password = "random-bs-go"

class UserManagerTest(TestCase):

    def test_create_user(self):
        User = get_user_model()
        test_email = f.email()
        phone_number = f.phone_number()
        user = User.objects.create_user(email=test_email, password=password, role="PASSENGER", phone_number=phone_number)

        self.assertEqual(test_email, user.email)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIsNone(user.username)

        with self.assertRaises(TypeError):
            User.objects.create_user()
        with self.assertRaises(TypeError):
            User.objects.create_user(email="")
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=password)
    

    def test_create_superuser(self):
        User = get_user_model()
        test_email = f.email()
        phone_number = f.phone_number()

        superuser = User.objects.create_superuser(email=test_email, password=password, role="ADMIN", phone_number=phone_number)
        
        self.assertEqual(test_email, superuser.email)
        self.assertTrue(superuser.is_active)
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertIsNone(superuser.username)

        with self.assertRaises(TypeError):
            User.objects.create_superuser()
        with self.assertRaises(TypeError):
            User.objects.create_superuser(email="")
        with self.assertRaises(ValueError):
            User.objects.create_superuser(email=test_email, password=password, is_superuser=False)

class UserSignupTest(APITestCase):
    def test_signup_success(self):
        data = {
            'email': 'test@example.com',
            'password': password,
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'Passenger',
            'phone_number': '3147878098'
        }
        response = self.client.post('/users/signup/', data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.first().role, 'Passenger')
    
    def test_signup_missing_fields(self):
        data = {'email': 'test@example.com'}
        response = self.client.post('/users/signup/', data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class LoginViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password=password,
            role='driver',
        )
    def test_login_success(self):
        data = {'email': 'test@example.com', 'password': password}
        response = self.client.post('/users/login/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data) 

    def test_login_wrong_password(self):
        data = {'email': 'test@example.com', 'password': 'wrongpass'}
        response = self.client.post('/users/login/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class LogoutViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password=password,
            role='driver',
            phone_number = f.phone_number()
        )
        response = self.client.post('/users/login/', {
            'email': 'test@example.com',
            'password': password,
        })
        self.token = response.data['token']

    def test_logout_success(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token)
        response = self.client.post('/users/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    def test_logout_without_auth(self):
        response = self.client.post('/users/logout/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
