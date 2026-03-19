from django.urls import path, include
from .views import GoogleLoginView

api_urlpatterns = [
    path('', include('dj_rest_auth.urls')),
    path('signup/', include('dj_rest_auth.registration.urls')),
    path('google/', GoogleLoginView.as_view(), name='google-login'),
]

urlpatterns = [
    path('api/', include(api_urlpatterns)),

    # Server-rendered pages (login, hello – added when building visual layer)
]