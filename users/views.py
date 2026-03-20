from django.shortcuts import render, redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model, login, logout, authenticate
from .serializers import UserSignupSerializer
# Create your views here.

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.views.decorators.http import require_GET
from allauth.socialaccount.helpers import complete_social_login
from allauth.exceptions import ImmediateHttpResponse
from dj_rest_auth.registration.views import SocialLoginView
from .forms import UserSignupForm

def login_page_view(request):
    error = request.GET.get('error')
    return render(request, 'users/login.html', {'error': error})


def signup_page_view(request):
    if request.method == 'POST':
        form = UserSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='users.backends.EmailAuthenticationBackend')
            if user.role == "driver":
                return redirect('driver_dashboard_page')
            elif user.role == "passenger":
                return redirect("passenger_dashboard")
            else:
                return redirect("admin_dashboard")
    else:
        form = UserSignupForm()
    return render(request, 'users/signup.html', {'form': form})

class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = 'http://localhost:8000/auth/callback'
    client_class = OAuth2Client

    def get_response(self):
        response = super().get_response()
        response.data['token'] = response.data.pop('key', None) 
        return response

@require_GET
def google_callback_view(request):
    try:
        from allauth.socialaccount.models import SocialLogin
        sociallogin = SocialLogin.deserialize(
            request.session.get("socialaccount_sociallogin", {})
        )
        response = complete_social_login(request, sociallogin)

        return response

    except ImmediateHttpResponse as e:
        return e.response
    
    except:
        return redirect('login_page')
#-----------------------------#
# API TOKEN BASED AUTH SYSTEM #
#-----------------------------#

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
    Token.objects.filter(user=request.user).delete() # delete api tokens
    logout(request) # logout any active browser logins i.e. django sessions

    if request.META.get('HTTP_AUTHORIZATION'): # check if its a api client
        return Response({'message': 'Logged out'}, status=status.HTTP_200_OK)

    # if there is not token sent, its a browser client => redirect to login page
    return redirect('session_login_page') 



