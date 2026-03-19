from rest_framework import serializers
from .models import Trip, TripNode, TripPassenger, CarPoolRequest, DriverOffer
class TripCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = ['max_passengers', 'start_node', 'end_node']

class CarPoolRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarPoolRequest
        fields = ['pickup', 'drop']

    
