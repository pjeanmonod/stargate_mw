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
        try:
            # 1️⃣ Generate UUID for run_id
            run_id = str(uuid.uuid4())

            # 2️⃣ Format payload for AWX
            job_vars = format_awx_request(request.data)
            job_vars["run_id"] = run_id
            awx_request = {"extra_vars": job_vars}

            # 3️⃣ Launch AWX workflow
            awx = AWX()
            response = awx.launch_build(awx_request)

            # 4️⃣ Ensure we have a dict
            if hasattr(response, "json"):
                awx_data = response.json()
            else:
                awx_data = response

            # 5️⃣ Extract AWX job ID
            awx_job_id = awx_data.get("id") or awx_data.get("workflow_job")
            if not awx_job_id:
                raise ValueError("AWX did not return a workflow/job ID")

            # 6️⃣ Extract run_id from extra_vars (JSON string)
            extra_vars_str = awx_data.get("extra_vars", "{}")
            try:
                extra_vars = json.loads(extra_vars_str)
                run_id_from_awx = extra_vars.get("run_id", run_id)
            except Exception:
                run_id_from_awx = run_id

            # 7️⃣ Save to DB correctly
            TerraformPlan.objects.update_or_create(
                run_id=run_id_from_awx,
                defaults={
                    "job_id": str(awx_job_id),
                    "plan_text": "",
                },
            )

            # 8️⃣ Return response to frontend
            return Response(
                {
                    "success": "Build successfully raised!",
                    "run_id": run_id_from_awx,
                    "job_id": awx_job_id,
                    "awx_response": awx_data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Error launching AWX job")
            return Response(
                {"error": f"Error encountered when submitting request: {str(e)}"},
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
def approve_terraform_plan(request, run_id):
    """Approve Terraform plan and continue the AWX workflow."""
    try:
        # Look up the Terraform plan by run_id
        plan = TerraformPlan.objects.filter(run_id=run_id).first()
        if not plan or not plan.job_id:
            return JsonResponse(
                {"error": "No matching AWX job_id found for this run_id."},
                status=404,
            )

        # Approve the workflow in AWX
        awx = AWX()
        response = awx.approve_workflow(plan.job_id)

        # Handle AWX response
        if response.status_code not in [200, 201, 204]:
            return JsonResponse(
                {"error": f"Failed to approve workflow: {response.status_code}"},
                status=response.status_code,
            )

        return JsonResponse(
            {"status": "approved", "run_id": run_id, "job_id": plan.job_id},
            status=200,
        )
    except Exception as e:
        logger.exception("Error approving workflow")
        return JsonResponse({"error": str(e)}, status=500)
