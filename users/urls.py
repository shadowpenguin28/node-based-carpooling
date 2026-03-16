from django.urls import path
from .views import user_signup_view, login_view, logout_view

urlpatterns = [
    path('signup/', user_signup_view, name='user_signup_view'),
    path('login/', login_view, name='user_login'),
    path('logout/', logout_view, name='user_logout'),
]