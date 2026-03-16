from django.db import models

# Create your models here.
class Node(models.Model):
    name = models.CharField(max_length='128')
    address = models.CharField(max_length='512')

class Edge(models.Model): 
    # Implements a one way edge by default : source => destination
    # For two way edges: A => B object and B => A object
    source = models.ForeignKey(Node, on_delete=models.CASCADE, help_text="Source Node", related_name="outgoing")
    destination = models.ForeignKey(Node, on_delete=models.CASCADE, help_text="Destination Node", related_name="incoming")
    distance = models.FloatField(help_text="Distance in km")

    class Meta:
        unique_together = ('source', 'destination')


