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
    Poll AWX for the job stdout, extract the terraform plan, save to DB (plan_text),
    and return 202 while pending or 200 with the plan when available.
    """

    def retrieve(self, request, pk=None):
        logger.info("Polling Terraform plan for job %s (request by %s)", pk, request.user)

        # Ensure there is a DB row for this job_id (create placeholder if needed)
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

        # Create AWX client and fetch job metadata & stdout
        awx = AWX()
        try:
            job_meta = awx.get_job(pk)  # must return a dict-like with 'status' or similar
        except Exception as e:
            logger.exception("Error fetching job metadata for job %s: %s", pk, e)
            # transient error — keep polling
            return Response({"status": "pending", "detail": "error fetching job metadata"}, status=status.HTTP_202_ACCEPTED)

        job_status = None
        try:
            # job_meta might be a requests.Response.json() or a dict-like object
            job_status = job_meta.get("status") if isinstance(job_meta, dict) else getattr(job_meta, "status", None)
        except Exception:
            job_status = None

        logger.info("AWX job %s status: %s", pk, job_status)

            # Fetch full stdout text using your AWX helper which calls /jobs/{id}/stdout/?format=txt
        try:
            stdout_response = awx.get_terraform_plan(pk)
        except Exception as e:
            logger.exception("Error fetching stdout for job %s: %s", pk, e)
            return Response(
                {"status": "pending", "detail": "error fetching job stdout"},
                status=status.HTTP_202_ACCEPTED
            )

        # Extract stdout text depending on type of response
        if isinstance(stdout_response, dict):
            stdout = stdout_response.get("msg", "")
        else:
            stdout = getattr(stdout_response, "text", "") or ""

        logger.info(
            "AWX stdout first 500 chars for job %s:\n%s",
            pk,
            stdout[:500].replace("\n", "\\n")
        )

        # Check if stdout_response indicates failure / not ready
        status_code = getattr(stdout_response, "status_code", None)
        if not stdout_response or status_code != 200:
            logger.info(
                "AWX stdout endpoint returned non-200 (%s) for job %s — still processing",
                status_code,
                pk
            )
            return Response({"status": "pending"}, status=status.HTTP_202_ACCEPTED)


        # --- Extraction strategies ---

        # Strategy A: explicit markers
        begin_marker = "===BEGIN_TERRAFORM_PLAN==="
        end_marker = "===END_TERRAFORM_PLAN==="

        start = stdout.find(begin_marker)
        end = stdout.find(end_marker)

        extracted = None

        if start != -1 and end != -1 and end > start:
            extracted = stdout[start + len(begin_marker):end].strip()
            logger.info("Found plan markers for job %s (marker strategy). Extracted length: %d", pk, len(extracted))
        else:
            # Strategy B: If markers not present, attempt to locate terraform show / Plan block heuristically.
            # Look for the common terraform intro line "Terraform used the selected providers"
            terraform_intro_re = re.compile(r"(Terraform used the selected providers[\s\S]+?)(?:Changes to Outputs:|Plan:|\Z)", re.IGNORECASE)
            m = terraform_intro_re.search(stdout)
            if m:
                extracted = m.group(0).strip()
                logger.info("Found terraform 'used the selected providers' block for job %s. Extracted length: %d", pk, len(extracted))
            else:
                # Strategy C: try to find the 'Plan:' summary and everything after it
                plan_re = re.compile(r"(Plan:.*?$[\s\S]*)", re.MULTILINE)
                m2 = plan_re.search(stdout)
                if m2:
                    # include some context: try to capture a reasonable chunk from near the Plan: line
                    # We'll take from 2000 chars before match start to the end (clamped)
                    start_idx = max(0, m2.start() - 2000)
                    extracted = stdout[start_idx:].strip()
                    logger.info("Found 'Plan:' section for job %s. Extracted length: %d", pk, len(extracted))

        # If we've got something, save it and update DB
        if extracted:
            try:
                plan.plan_text = extracted
                # Set status to 'completed' (or 'done' depending on your model choices)
                # If your model uses a status field name different from plan.status, adjust accordingly.
                try:
                    plan.status = "completed"
                except Exception:
                    # if model doesn't have status field, ignore
                    pass
                logger.info("About to save plan for job %s, length %d", pk, len(extracted))
                plan.save()
                logger.info("Saved terraform plan for job %s into DB (TerraformPlan id=%s)", pk, plan.id)
                return Response({"status": "completed", "plan_text": plan.plan_text}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.exception("Failed to save extracted plan for job %s: %s", pk, e)
                return Response({"error": "failed to save plan"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If job is explicitly failed, save stdout for debugging
        if job_status and str(job_status).lower() in ("failed", "error"):
            try:
                plan.plan_text = stdout[:100000]  # store some stdout for debugging
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

        # Otherwise the job is likely still running or stdout is not yet ready
        logger.info("Plan not yet extractable for job %s; returning pending.", pk)
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
