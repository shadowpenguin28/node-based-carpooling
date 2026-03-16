from django.test import TestCase
from django.contrib.auth import get_user_model
from faker import Faker
# Create your tests here.

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


