from rest_framework import serializers
from .models import BuildRequest

class BuildRequestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = BuildRequest
        fields = ('request_id', 'job_data', 'master_ticket')