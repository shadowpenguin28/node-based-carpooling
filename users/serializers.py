
from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import TokenSerializer

from rest_framework import serializers

class CustomRegisterSerializer(RegisterSerializer):
    username = None  # remove username field

    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    role = serializers.ChoiceField(choices=["driver", "passenger", "admin"], required=True)
    phone_number = serializers.CharField(max_length=10, required=True)
    gender = serializers.CharField(required=False)
    dob = serializers.DateField(required=False)

    def save(self, request):
        user = super().save(request)
        user.first_name = self.validated_data['first_name']
        user.last_name = self.validated_data['last_name']
        user.role = self.validated_data['role']
        user.phone_number = self.validated_data['phone_number']
        user.gender = self.validated_data.get('gender')
        user.dob = self.validated_data.get('dob')
        user.save()
        return user

class CustomTokenSerializer(TokenSerializer):
    token = serializers.CharField(source='key')

    class Meta(TokenSerializer.Meta):
        fields = ('token',)

# PREVIOUS REST FRAMEWORK AUTHENTICATION SETUP
# from rest_framework import serializers
# from django.contrib.auth import get_user_model

# User = get_user_model()

# class UserSignupSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User
#         fields = ['email', 'password', 'first_name', 'last_name', 'role', 'gender', 'dob', 'phone_number']
#         extra_kwargs = {
#             'password': {'write_only': True},
#         }

#     def create(self, validated_data):
#         user = User.objects.create_user(**validated_data)
#         return user
