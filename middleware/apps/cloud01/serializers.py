from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import BuildRequest
from .models import InfraOutput
from .models import TerraformPlan

class InfraOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = InfraOutput
        fields = ["key", "id", "value", "updated_at"]

class TerraformPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerraformPlan
        fields = ['job_id', 'plan_text', 'created_at']

class BuildRequestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = BuildRequest
        fields = ('request_id', 'job_data', 'master_ticket')

class JobStatusSerializer(serializers.ModelSerializer):
    plan_status = serializers.SerializerMethodField()
    state_status = serializers.SerializerMethodField()

    class Meta:
        model = TerraformPlan
        fields = ["run_id", "job_id", "plan_text", "created_at", "plan_status", "state_status"]

    def get_plan_status(self, obj):
        # derive from presence of plan_text
        return "ready" if obj.plan_text else "pending"

    def get_state_status(self, obj):
        # you can improve this later; for now:
        return None

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