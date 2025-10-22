from django.http import JsonResponse
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.decorators import action
import traceback
from pprint import pprint
import uuid

from .models import BuildRequest, InfraOutput, TerraformPlan
from .serializers import InfraOutputSerializer, CustomTokenObtainPairSerializer
from .awx import AWX
from .input_handler import format_awx_request
import logging
import re

logger = logging.getLogger(__name__)


# -------------------- #
#  InfraOutput CRUD
# -------------------- #
class InfraOutputViewSet(viewsets.ModelViewSet):
    queryset = InfraOutput.objects.all()
    serializer_class = InfraOutputSerializer


# -------------------- #
#  JWT Authentication
# -------------------- #
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


# ------------------------------------- #
#  Configure / Launch Terraform Plan    #
# ------------------------------------- #
class configure(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, format=None):
        """
        Receives payload from frontend, formats it, triggers AWX Terraform plan workflow,
        and stores mapping between run_id and workflow_job_id.
        """
        try:
            # Generate a unique run_id (keep your existing UUID logic)
            run_id = str(uuid.uuid4())
            data = request.data

            # Format payload for AWX
            job_vars = format_awx_request(data)
            job_vars["run_id"] = run_id  # Ensure run_id is included
            awx_request = {"extra_vars": job_vars}

            # Launch the AWX workflow
            awx = AWX()
            awx_response = awx.launch_build(awx_request)

            # Extract workflow job ID
            awx_workflow_id = awx_response.get("id") or awx_response.get("workflow_job_id")

            # Save mapping in DB (TerraformPlan)
            TerraformPlan.objects.update_or_create(
                run_id=run_id,
                defaults={
                    "workflow_job_id": awx_workflow_id,
                    "plan_text": "",  # Keep empty initially
                },
            )

            # Return response
            return Response(
                {
                    "success": "Build successfully raised!",
                    "run_id": run_id,
                    "workflow_job_id": awx_workflow_id,
                    "awx_response": awx_response,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Error launching AWX job")
            return Response(
                {"error": "Error encountered when submitting request.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
# ---------------------- #
#  Get Terraform Plan  #
# ---------------------- #

class TerraformPlanViewSet(viewsets.ViewSet):
    """
    Handles receiving Terraform plan output from Ansible
    and serving it to the frontend when requested.
    """

    def create(self, request):
        """
        POST /api/cloud01/infra/terraform/plan/
        Called by Ansible when the staging playbook finishes.

        Body:
        {
            "job_id": "894",
            "plan_text": "Terraform plan output..."
        }
        """
        try:
            job_id = request.data.get("job_id")
            plan_text = request.data.get("plan_text")

            if not job_id or not plan_text:
                return Response(
                    {"error": "Missing job_id or plan_text"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update or create the TerraformPlan record
            plan, _ = TerraformPlan.objects.update_or_create(
                job_id=job_id,
                defaults={"plan_text": plan_text}
            )

            return Response(
                {"message": f"Terraform plan stored for job {plan.job_id}"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, pk=None):
        """
        GET /api/cloud01/infra/terraform/plan/<job_id>/
        Called by the frontend to check if the plan is available.
        """
        try:
            plan = TerraformPlan.objects.filter(job_id=pk).first()
            if not plan:
                return Response(
                    {"status": "pending", "message": "Plan not yet received"},
                    status=status.HTTP_202_ACCEPTED
                )

            return Response(
                {"job_id": plan.job_id, "plan_text": plan.plan_text},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ------------------------ #
#  Approve Terraform Plan  #
# ------------------------ #
@api_view(["POST"])
def approve_terraform_plan(request, job_id):
    """Approve Terraform plan and continue workflow."""
    try:
        awx = AWX()
        response = awx.approve_workflow(job_id)

        if response.status_code not in [200, 201, 204]:
            return JsonResponse(
                {"error": f"Failed to approve workflow: {response.status_code}"},
                status=response.status_code,
            )

        return JsonResponse({"status": "approved", "job_id": job_id})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
