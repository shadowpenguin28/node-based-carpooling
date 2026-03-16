from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _

class CustomUserManager(BaseUserManager):

    def create_user(self, email, password, **extra_fields):
        """
        Custom create user function to create a user with given email and password
        """
        if not email:
            raise ValueError(_("The email must be set"))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()

        return user
    
    def create_superuser(self, email, password, **extra_fields):
        """
        Superuser create function that creates a super user with given email and password 
        """
        fields = ["is_staff", "is_superuser", "is_active"]
        for field in fields:
            extra_fields.setdefault(field, True)
        
        if not extra_fields.get("is_staff"):
            raise ValueError(_("Superuser must be staff!"))
        if not extra_fields.get("is_superuser"):
            raise ValueError(_("Superuser must have is_superuser set to True"))
        
        return self.create_user(email, password, **extra_fields)
