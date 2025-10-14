from django.http import JsonResponse
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
import traceback
from pprint import pprint

from .models import BuildRequest, InfraOutput, TerraformPlan
from .serializers import InfraOutputSerializer, CustomTokenObtainPairSerializer
from .awx import AWX
from .input_handler import format_awx_request


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
#  Configure / Launch Terraform Plan  #
# ------------------------------------- #
class configure(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, format=None):
        """
        Receives payload from frontend, formats, and triggers AWX Terraform plan workflow.
        """
        try:
            data = self.request.data
            pprint(data, indent=3)

            # Convert frontend payload → AWX format
            job_vars = format_awx_request(data)
            awx_request = {"extra_vars": job_vars}
            pprint(awx_request)

            # Launch AWX job via helper class
            awx = AWX()
            awx_response = awx.launch_build(awx_request)

            # Return AWX job info (expecting job_id)
            return Response(
                {
                    "success": "build successfully raised!",
                    "awx_response": awx_response,
                },
                status=200,
            )

        except Exception as e:
            print("Error launching AWX job:", e)
            return Response(
                {
                    "error": "Error encountered when submitting request.",
                    "stacktrace": traceback.format_exc(),
                },
                status=500,
            )


# ---------------------- #
#  Get Terraform Plan  #
# ---------------------- #
class TerraformPlanViewSet(viewsets.ViewSet):
    """
    Retrieves Terraform plan status and output.
    Polls AWX job and stores TF plan in DB once available.
    """

    def retrieve(self, request, pk=None):
        try:
            plan = TerraformPlan.objects.get(awx_job_id=pk)
        except TerraformPlan.DoesNotExist:
            return Response(
                {"message": "Plan not found yet."},
                status=status.HTTP_202_ACCEPTED
            )

        # Poll AWX only if plan is still pending
        if plan.status == "pending":
            awx = AWX()
            job = awx.get_job(plan.awx_job_id)  # Replace with actual AWX API call
            stdout = getattr(job, "stdout", "")

            if getattr(job, "status", None) == "successful":
                # Parse TF plan from AWX stdout
                begin_marker = "===BEGIN_TERRAFORM_PLAN==="
                end_marker = "===END_TERRAFORM_PLAN==="

                start = stdout.find(begin_marker)
                end = stdout.find(end_marker)

                if start != -1 and end != -1 and end > start:
                    plan_text = stdout[start + len(begin_marker):end].strip()
                    plan.tfplan_text = plan_text
                else:
                    plan.tfplan_text = "Could not parse Terraform plan from AWX stdout."

                plan.status = "completed"
                plan.save()

            elif getattr(job, "status", None) == "failed":
                plan.status = "failed"
                plan.tfplan_text = stdout  # save stdout for debugging
                plan.save()

        # Return current plan status
        if plan.status == "pending":
            return Response({"status": "pending"}, status=status.HTTP_202_ACCEPTED)
        elif plan.status == "failed":
            return Response(
                {"status": "failed", "tfplan_text": plan.tfplan_text},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        else:
            return Response(
                {"status": "completed", "tfplan_text": plan.tfplan_text},
                status=status.HTTP_200_OK
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
