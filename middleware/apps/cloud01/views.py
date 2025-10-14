from django.http import JsonResponse
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from .utils import save_terraform_plan
import traceback
from pprint import pprint

from .models import BuildRequest, InfraOutput, TerraformPlan
from .serializers import (
    InfraOutputSerializer,
    CustomTokenObtainPairSerializer,
)
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
    def retrieve(self, request, pk=None):
        try:
            plan = TerraformPlan.objects.get(job_id=pk)
        except TerraformPlan.DoesNotExist:
            return Response(
                {"message": "Plan not ready yet."},
                status=status.HTTP_202_ACCEPTED
            )

        if not plan.plan_text:
            return Response(
                {"message": "Plan still processing."},
                status=status.HTTP_202_ACCEPTED
            )

        return Response({"plan": plan.plan_text}, status=status.HTTP_200_OK)
    

class TerraformCallbackView(APIView):
    def post(self, request):
        job_id = request.data.get("job_id")
        plan_output = request.data.get("plan_output")

        if not job_id or not plan_output:
            return Response({"error": "Missing job_id or plan_output"}, status=400)

        # Save the plan in DB
        save_terraform_plan(job_id, plan_output)

        return Response({"status": "plan saved"}, status=status.HTTP_200_OK)



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