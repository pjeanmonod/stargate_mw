from django.http import JsonResponse
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.decorators import action
import json
import traceback
from pprint import pprint
import uuid

from .models import InfraOutput, TerraformPlan
from .serializers import InfraOutputSerializer, CustomTokenObtainPairSerializer, TerraformPlanSerializer
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


class TerraformPlanViewSet(viewsets.ModelViewSet):
    queryset = TerraformPlan.objects.all()
    serializer_class = TerraformPlanSerializer

    def create(self, request, *args, **kwargs):
        # Extract the AWX job/run ID
        run_id = request.data.get("job_id")  # this is the actual run UUID

        if not run_id:
            return Response(
                {"error": "job_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create the TerraformPlan by run_id
        terraform_plan, created = TerraformPlan.objects.get_or_create(run_id=run_id)

        # Update or set other fields from payload
        terraform_plan.plan_text = request.data.get("plan_text", terraform_plan.plan_text)
        terraform_plan.save()

        serializer = self.get_serializer(terraform_plan)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        """
        GET /api/cloud01/infra/terraform/plan/<run_id>/
        Called by the frontend to check if the plan is available.
        """
        try:
            plan = TerraformPlan.objects.filter(run_id=pk).first()
            if not plan:
                return Response(
                    {"status": "pending", "message": "Plan not yet received"},
                    status=status.HTTP_202_ACCEPTED
                )

            return Response(
                {"run_id": plan.run_id, "job_id": plan.job_id, "plan_text": plan.plan_text},
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
        # Success response for frontend snackbar
        return JsonResponse(
            {
                "success": True,
                "message": f"Terraform plan {run_id} approved successfully.",
                "run_id": run_id,
                "job_id": plan.job_id,
            },
            status=200,
        )

    except Exception as e:
        logger.exception("Error approving workflow")
        return JsonResponse({"success": False, "message": str(e)}, status=500)
    

# ------------------------- #
#  Approve Terraform Destroy #
# ------------------------- #

@api_view(["POST"])
def destroy_all_infra(request, run_id):
    """Approve Terraform destroy workflow via AWX."""
    try:
        # 1️⃣ Delete DB entries
        InfraOutput.objects.all().delete()
        # 1️⃣ Look up the Terraform plan by run_id
        plan = TerraformPlan.objects.filter(run_id=run_id).first()
        if not plan or not plan.job_id:
            return JsonResponse(
                {"error": "No matching AWX job_id found for this run_id."},
                status=404,
            )

        # 2️⃣ Approve the destroy workflow in AWX (approval node)
        awx = AWX()
        response = awx.approve_destroy_workflow(plan.job_id)  # same AWX method as plan approval

        # 3️⃣ Handle AWX response
        if response.status_code not in [200, 201, 204]:
            return JsonResponse(
                {
                    "error": f"Failed to approve destroy workflow: {response.status_code}",
                    "details": response.text,
                },
                status=response.status_code,
            )

        # 4️⃣ (Optional) Clean up middleware database after approval
        from .models import Infra
        Infra.objects.all().delete()

        # 5️⃣ Return success
        return JsonResponse(
            {
                "success": True,
                "message": f"Terraform destroy for run {run_id} approved successfully.",
                "run_id": run_id,
                "job_id": plan.job_id,
            },
            status=200,
        )

    except Exception as e:
        logger.exception("Error approving destroy workflow")
        return JsonResponse({"success": False, "message": str(e)}, status=500)
