from rest_framework import permissions
from django.contrib.auth import get_user_model

User = get_user_model()
class IsAdmin(permissions.BasePermission):
    message = 'Must be admin'

    def has_permission(self, request, view):
        if request.user and request.user.role == "admin":
            return True
        
        return False

class IsDriver(permissions.BasePermission):
    message = 'Must be driver'
    def has_permission(self, request, view):
        if request.user and request.user.role == "driver":
            return True
        
        return False

class IsPassenger(permissions.BasePermission):
    message = 'Must be passenger'
    def has_permission(self, request, view):
        if request.user and request.user.role == "passenger":
            return True
        
        return False