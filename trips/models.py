from django.db import models
from django.conf import settings
from core.models import Node
from core.graph import find_shortest_path, get_neighbours, nodes_in_n_hops

# Create your models here.
class Trip(models.Model):

    class Status(models.TextChoices):
        PLANNED = ("planned", "Planned")
        ACTIVE = ("active", "Active")
        COMPLETED = ("completed", "Completed")
        CANCELLED = ("cancelled", "Cancelled")
    
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)

    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='trip_driver',
        null=True,
        blank=True,
        limit_choices_to={"role": "driver"}, 
        help_text="Driver of the trip"
        )
    passengers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='trip_passengers',
        through="TripPassenger",
        help_text="Users (role: Passenger) onboard trip"
    )
    max_passengers = models.IntegerField(help_text="Maximum passengners allowed on trip")

    start_node = models.ForeignKey(Node, on_delete=models.PROTECT, related_name='start_node')
    end_node = models.ForeignKey(Node, on_delete=models.PROTECT, related_name='end_node')
    current_node = models.ForeignKey(Node, on_delete=models.PROTECT, related_name='current_node', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_route(self):
        pass

class TripNode(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    node = models.ForeignKey(Node, on_delete=models.PROTECT)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']
        unique_together = [('trip', 'order')]

class TripPassenger(models.Model):
    class BoardingStatus(models.TextChoices):
        PENDING  = ("pending",  "Pending")
        BOARDED  = ("boarded",  "Boarded")
        NO_SHOW  = ("no_show",  "No Show")
        DROPPED  = ("dropped",  "Dropped Off")

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    passenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, limit_choices_to={"role":"passenger"})
    boarding_status = models.CharField(max_length=12, choices=BoardingStatus.choices, default=BoardingStatus.PENDING)
    fare = models.FloatField(null=True, blank=True)

    pickup = models.ForeignKey(Node, on_delete=models.PROTECT, related_name="+")
    drop = models.ForeignKey(Node, on_delete=models.PROTECT, related_name="+")

    class Meta:
        unique_together = [("trip", "passenger")] 

