from django.urls import path
from .views import create_edge_view, create_node_view, retrieve_edge_view, retrieve_node_view, update_edge_view, update_node_view, delete_edge_view, delete_node_view
urlpatterns = [
    path('nodes/create/', create_node_view, name='create_node'),
    path('nodes/<int:pk>/', retrieve_node_view, name='retrieve_node'),
    path('nodes/<int:pk>/update/', update_node_view, name='update_node'),
    path('nodes/<int:pk>/delete/', delete_node_view, name='delete_node'),
    path('edges/create/', create_edge_view, name='create_edge'),
    path('edges/<int:pk>/', retrieve_edge_view, name='retrieve_edge'),
    path('edges/<int:pk>/update/', update_edge_view, name='update_edge'),
    path('edges/<int:pk>/delete/', delete_edge_view, name='delete_edge'),
]
