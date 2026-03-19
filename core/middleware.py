from django.http import JsonResponse
from core.models import ServiceConfig


class ServiceActiveMiddleware:
    """
    Middleware that blocks carpool-related requests when the service is suspended.
    Admin endpoints and authentication endpoints are exempt.
    """

    EXEMPT_PREFIXES = [
        '/admin/',
        '/users/',
        '/core/',
        '/trips/admin/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for prefix in self.EXEMPT_PREFIXES:
            if request.path.startswith(prefix):
                return self.get_response(request)

        # Check if service is active
        if not ServiceConfig.is_service_active():
            return JsonResponse(
                {'error': 'Carpooling service is currently suspended by admin.'},
                status=503,
            )

        return self.get_response(request)
