from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model, authenticate, login, logout
from .serializers import UserSignupSerializer
# Create your views here.

User = get_user_model()

# User signup view
@api_view(['GET', 'POST'])
def user_signup_view(request):

    if request.method != 'POST':
        return Response(data={
            "email": "Valid email",
            "first_name": "Add first_name (REQUIRED)",
            "last_name": "Add last_name (REQUIRED)",
            "role": "DRIVER/PASSENGER/ADMIN (REQUIRED)",
            "gender": "Add gender",
            "dob": "Add date of birth",
            "phone_numer": "Add phone number (REQUIRED)"
        })
    serializer = UserSignupSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    # errors
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def login_view(request):
    user = authenticate(request, email=request.data.get('email', None), password=request.data.get('password', None))

    if user != None:
        login(request, user)
        token, created = Token.objects.get_or_create(user=user)
        return Response(data={
            'token': token.key,
            'user_id': user.id,
            'role': user.role,
        }, status=status.HTTP_200_OK)
    
    return Response(data={"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    request.user.auth_token.delete()
    logout(request)
    return Response(data={
        'message': 'Logged out',
    }, status=status.HTTP_200_OK)



