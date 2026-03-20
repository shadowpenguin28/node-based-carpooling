from django.urls import path, include
from .views import (
    login_page_view, signup_page_view,
    user_signup_view, login_view, logout_view
)

api_urlpatterns = [
    path('signup/', user_signup_view, name='api_user_signup'),
    path('login/', login_view, name='api_user_login'),
    path('logout/', logout_view, name='api_user_logout'),
]

urlpatterns = [
    path('api/', include(api_urlpatterns)),
    path("login/", login_page_view, name="session_login_page"),
    path("signup/", signup_page_view, name="user_signup"),
    path("logout/", logout_view, name="session_logout"),
    path("auth/", include("allauth.urls")),
]