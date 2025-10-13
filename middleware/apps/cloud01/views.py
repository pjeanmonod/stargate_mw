from django.http import JsonResponse
from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
import traceback
from pprint import pprint

from .models import BuildRequest, InfraOutput
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
@api_view(["GET"])
def get_terraform_plan(request, job_id):
    """
    Fetch Terraform plan output for given AWX job.
    """
    try:
        awx = AWX()
        plan_url = f"{awx.url}jobs/{job_id}/stdout/?format=txt"
        response = awx.session.get(plan_url, verify=False)

        if response.status_code == 404 or not response.text.strip():
            return Response({"status": "pending"}, status=202)

        stdout = response.text

        # Extract plan between markers
        import re
        match = re.search(r"===BEGIN_TERRAFORM_PLAN===(.*?)===END_TERRAFORM_PLAN===", stdout, re.DOTALL)
        if not match:
            # Still running or not yet printed
            return Response({"status": "pending"}, status=202)

        plan_text = match.group(1).strip()

        return Response({
            "status": "ready",
            "job_id": job_id,
            "plan": plan_text
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)



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