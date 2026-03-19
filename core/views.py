from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .permissions import IsAdmin
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status

from .models import Node, Edge
from .serializers import NodeSerializer, EdgeSerializer
# Create your views here.

def landing_page_view(request):
    return render(request, 'core/index.html')

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def create_node_view(request):
    serializer = NodeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save() 
        return Response(data = serializer.data, status=status.HTTP_201_CREATED)

    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def retrieve_node_view(request, pk):
    try:
        node = Node.objects.get(pk=pk)
    except Node.DoesNotExist:
        return Response(data={"errors": "Node object not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = NodeSerializer(node)
    return Response(data = serializer.data, status=status.HTTP_200_OK)

@api_view(['PUT'])
@permission_classes([IsAuthenticated, IsAdmin])
def update_node_view(request, pk):
    try:
        node = Node.objects.get(pk=pk)
    except Node.DoesNotExist:
        return Response(data={"errors": "Node object not found"}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = NodeSerializer(node, data = request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(data = serializer.data, status=status.HTTP_200_OK)
    
    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsAdmin])
def delete_node_view(request, pk):
    try:
        node = Node.objects.get(pk=pk)
    except Node.DoesNotExist:
        return Response(data={"errors": "Node object not found"}, status=status.HTTP_404_NOT_FOUND)
    
    node.delete()
    return Response(data={"message": "Node successfully deleted"}, status=status.HTTP_200_OK) 

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def create_edge_view(request):
    serializer = EdgeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(data = serializer.data, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def retrieve_edge_view(request, pk):
    try:
        edge = Edge.objects.get(pk=pk)
    except Edge.DoesNotExist:
        return Response(data={"errors": "Edge object not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = EdgeSerializer(edge)
    return Response(data = serializer.data, status=status.HTTP_200_OK)

@api_view(['PUT'])
@permission_classes([IsAuthenticated, IsAdmin])
def update_edge_view(request, pk):
    try:
        edge = Edge.objects.get(pk=pk)
    except Edge.DoesNotExist:
        return Response(data={"errors": "Edge object not found"}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = EdgeSerializer(edge, data = request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(data = serializer.data, status=status.HTTP_200_OK)
    
    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsAdmin])
def delete_edge_view(request, pk):
    try:
        edge = Edge.objects.get(pk=pk)
    except Edge.DoesNotExist:
        return Response(data={"errors": "Edge object not found"}, status=status.HTTP_404_NOT_FOUND)

    edge.delete()
    return Response(data={"message": "Edge successfully deleted"}, status=status.HTTP_200_OK)
