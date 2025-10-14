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
    Poll AWX for the job stdout (handling workflow jobs), extract the terraform plan,
    save to DB (plan_text), and return 202 while pending or 200 with the plan when available.
    """

    def retrieve(self, request, pk=None):
        logger.info("Polling Terraform plan for job %s (request by %s)", pk, request.user)

        # Ensure there is a DB row for this job_id
        try:
            plan, created = TerraformPlan.objects.get_or_create(job_id=pk)
            if created:
                logger.info("Created placeholder TerraformPlan DB row for job %s", pk)
        except Exception as e:
            logger.exception("DB error getting/creating TerraformPlan for job %s: %s", pk, e)
            return Response({"error": "DB error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If plan already present, return immediately
        if plan.plan_text:
            logger.info("Plan already present in DB for job %s (id=%s), returning", pk, plan.id)
            return Response({"status": "completed", "plan_text": plan.plan_text}, status=status.HTTP_200_OK)

        awx = AWX()
        job_status = None
        stdout = ""

        try:
            job_meta = awx.get_job(pk)
            job_status = job_meta.get("status") if isinstance(job_meta, dict) else getattr(job_meta, "status", None)
            logger.info("AWX job %s status: %s", pk, job_status)

            # If this is a workflow job, locate the staging child job
            if isinstance(job_meta, dict) and job_meta.get("type") == "workflow_job":
                nodes = awx.get_workflow_nodes(pk)
                # naive assumption: first successful child job is the staging plan
                child_job_id = None
                for node in nodes.get("results", []):
                    uj = node.get("unified_job")
                    if uj and uj.get("job_type") == "run" and "staging" in node.get("name", "").lower():
                        child_job_id = uj.get("id")
                        break
                if not child_job_id:
                    logger.info("No staging child job found for workflow job %s; still pending", pk)
                    return Response({"status": "pending"}, status=status.HTTP_202_ACCEPTED)
                logger.info("Found staging child job %s for workflow job %s", child_job_id, pk)
                pk = child_job_id  # override pk to fetch stdout from actual job

            # Fetch stdout from the actual job (child or normal job)
            stdout_response = awx.get_terraform_plan(pk)
            if isinstance(stdout_response, dict):
                stdout = stdout_response.get("msg", "")
            else:
                stdout = getattr(stdout_response, "text", "") or ""

            logger.info("AWX stdout first 500 chars for job %s:\n%s", pk, stdout[:500].replace("\n", "\\n"))

        except Exception as e:
            logger.exception("Error fetching job/stdout for job %s: %s", pk, e)
            return Response({"status": "pending", "detail": "error fetching job/stdout"}, status=status.HTTP_202_ACCEPTED)

        # --- Extraction strategies ---
        extracted = None
        begin_marker = "===BEGIN_TERRAFORM_PLAN==="
        end_marker = "===END_TERRAFORM_PLAN==="
        start = stdout.find(begin_marker)
        end = stdout.find(end_marker)

        if start != -1 and end != -1 and end > start:
            extracted = stdout[start + len(begin_marker):end].strip()
            logger.info("Found plan markers for job %s (marker strategy). Extracted length: %d", pk, len(extracted))
        else:
            # Strategy B: Terraform intro
            terraform_intro_re = re.compile(r"(Terraform used the selected providers[\s\S]+?)(?:Changes to Outputs:|Plan:|\Z)", re.IGNORECASE)
            m = terraform_intro_re.search(stdout)
            if m:
                extracted = m.group(0).strip()
                logger.info("Found terraform 'used the selected providers' block for job %s. Extracted length: %d", pk, len(extracted))
            else:
                # Strategy C: 'Plan:' summary
                plan_re = re.compile(r"(Plan:.*?$[\s\S]*)", re.MULTILINE)
                m2 = plan_re.search(stdout)
                if m2:
                    start_idx = max(0, m2.start() - 2000)
                    extracted = stdout[start_idx:].strip()
                    logger.info("Found 'Plan:' section for job %s. Extracted length: %d", pk, len(extracted))

        # Save extracted plan
        if extracted:
            try:
                plan.plan_text = extracted
                try:
                    plan.status = "completed"
                except Exception:
                    pass
                plan.save()
                logger.info("Saved terraform plan for job %s into DB (TerraformPlan id=%s)", pk, plan.id)
                return Response({"status": "completed", "plan_text": plan.plan_text}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.exception("Failed to save extracted plan for job %s: %s", pk, e)
                return Response({"error": "failed to save plan"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Job failed or stdout not ready
        if job_status and str(job_status).lower() in ("failed", "error"):
            try:
                plan.plan_text = stdout[:100000]
                try:
                    plan.status = "failed"
                except Exception:
                    pass
                plan.save()
                logger.info("Job %s failed; saved stdout to plan_text for debugging.", pk)
                return Response({"status": "failed", "plan_text": plan.plan_text}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                logger.exception("Failed to save stdout on failure for job %s: %s", pk, e)
                return Response({"error": "failed to save stdout"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "pending"}, status=status.HTTP_202_ACCEPTED)

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
