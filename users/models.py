from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from .managers import CustomUserManager
# Create your models here.


class User(AbstractUser):
    USER_ROLES = (
        ("driver", "Driver"),
        ("passenger", "Passenger"),
        ("admin", "Admin")
    )

    username = None
    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(max_length=32)
    last_name = models.CharField(max_length=32)

    role = models.CharField(max_length=10, choices=USER_ROLES)
    gender = models.CharField(max_length=10, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=10) # working with only Indian Phone Numbers

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = ["first_name", "last_name", "role", "phone_number"]
    objects = CustomUserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
