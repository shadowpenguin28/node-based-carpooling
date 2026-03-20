from django.urls import path, include
from .views import (
    create_trip_view, start_trip_view, advance_trip_view, cancel_trip_view,
    create_carpool_request, view_driver_offers, accept_driver_offer,
    cancel_carpool_request,
    view_carpool_requests, create_driver_offer,
    fetch_driver_trips, trip_dashboard, driver_dashboard_page,
    passenger_dashboard_page, admin_dashboard_page,
    admin_view_active_trips, admin_toggle_service, board_passenger, dropoff_passenger,
    top_up_wallet, wallet_transactions,
)

api_urlpatterns = [
    # Trip lifecycle (Driver)
    path('create/', create_trip_view, name='create_trip'),
    path('<int:trip_id>/start/', start_trip_view, name='start_trip'),
    path('<int:trip_id>/advance/', advance_trip_view, name='advance_trip'),
    path('<int:trip_id>/cancel/', cancel_trip_view, name='cancel_trip'),
    path('<int:trip_id>/dashboard/', trip_dashboard, name='trip_dashboard'),
    path('mine/', fetch_driver_trips, name='fetch_driver_trips'),
    path('<int:trip_id>/board/<int:passenger_id>/', board_passenger, name='board_passenger'),
    path('<int:trip_id>/dropoff/<int:passenger_id>/', dropoff_passenger, name='dropoff_passenger'),

    # Carpool request (Passenger)
    path('carpool/request/', create_carpool_request, name='create_carpool_request'),
    path('carpool/request/<int:cr_id>/offers/', view_driver_offers, name='view_driver_offers'),
    path('carpool/request/<int:req_id>/accept/<int:offer_id>/', accept_driver_offer, name='accept_driver_offer'),
    path('carpool/request/<int:cr_id>/cancel/', cancel_carpool_request, name='cancel_carpool_request'),

    # Driver carpool actions
    path('carpool/requests/', view_carpool_requests, name='view_carpool_requests'),
    path('carpool/request/<int:req_id>/offer/', create_driver_offer, name='create_driver_offer'),

    # Admin
    path('admin/active/', admin_view_active_trips, name='admin_view_active_trips'),
    path('admin/service/toggle/', admin_toggle_service, name='admin_toggle_service'),

    # Wallet
    path('wallet/topup/', top_up_wallet, name='top_up_wallet'),
    path('wallet/transactions/', wallet_transactions, name='wallet_transactions'),
]

urlpatterns = [
    path('api/', include(api_urlpatterns)),

    # Server-rendered pages
    path('dashboard/', driver_dashboard_page, name='driver_dashboard_page'),
    path('passenger_dashboard/', passenger_dashboard_page, name='passenger_dashboard'),
    path('admin_dashboard/', admin_dashboard_page, name='admin_dashboard'),
]
