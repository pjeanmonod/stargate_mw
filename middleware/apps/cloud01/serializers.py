from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import BuildRequest

class BuildRequestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = BuildRequest
        fields = ('request_id', 'job_data', 'master_ticket')

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
        }
        # Add custom user-related data (e.g., vendor info)
        return data