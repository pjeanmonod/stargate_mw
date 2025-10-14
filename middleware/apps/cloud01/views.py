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
    Poll AWX for the job stdout (handling workflow jobs),
    extract the Terraform plan, save to DB (plan_text),
    and return 202 while pending or 200 with the plan when available.
    """

    def retrieve(self, request, pk=None):
        logger.info("Polling Terraform plan for job %s (request by %s)", pk, request.user)

        # --- Ensure there is a DB row for this job_id ---
        try:
            plan, created = TerraformPlan.objects.get_or_create(job_id=pk)
            if created:
                logger.info("Created placeholder TerraformPlan DB row for job %s", pk)
        except Exception as e:
            logger.exception("DB error getting/creating TerraformPlan for job %s: %s", pk, e)
            return Response({"error": "DB error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- If already completed, return immediately ---
        if plan.plan_text:
            logger.info("Plan already present in DB for job %s (id=%s), returning", pk, plan.id)
            return Response({"status": "completed", "plan_text": plan.plan_text}, status=status.HTTP_200_OK)

        awx = AWX()
        stdout = ""
        job_status = None

        # --- Fetch workflow/job metadata ---
        try:
            job_meta = awx.get_job(pk)
        except Exception as e:
            logger.exception("Error fetching job metadata for job %s: %s", pk, e)
            return Response({"status": "pending", "detail": "error fetching job metadata"}, status=status.HTTP_202_ACCEPTED)

             # --- Determine which job actually has stdout with Terraform plan in it ---
        actual_job_id = pk

        if job_meta.get("type") == "workflow_job":
            try:
                terraform_node = None

                # Try summary_fields first
                nodes = job_meta.get("summary_fields", {}).get("workflow_nodes") or []

                # If not present, call AWX API directly to list workflow nodes
                if not nodes:
                    nodes_url = f"workflow_jobs/{pk}/workflow_nodes/"
                    logger.info("Fetching workflow nodes from AWX: %s", nodes_url)
                    nodes_resp = awx.session.get(awx.url + nodes_url, auth=awx.auth, verify=False)
                    nodes_resp.raise_for_status()
                    nodes = nodes_resp.json().get("results", [])

                logger.info("Found %d workflow nodes for workflow job %s", len(nodes), pk)

                # Look for a node whose job name contains 'stage' or 'terraform'
                for node in nodes:
                    node_job = node.get("summary_fields", {}).get("job")
                    if node_job and any(keyword in node_job.get("name", "").lower() for keyword in ["stage", "terraform"]):
                        terraform_node = node_job
                        break

                if terraform_node:
                    actual_job_id = terraform_node["id"]
                    logger.info(
                        "Found child job %s (%s) for workflow job %s",
                        actual_job_id,
                        terraform_node["name"],
                        pk,
                    )
                else:
                    logger.warning(
                        "No Stage/Terraform node found in workflow job %s; using workflow job stdout fallback",
                        pk,
                    )

            except Exception as e:
                logger.exception("Error traversing workflow nodes for workflow job %s: %s", pk, e)
 

        # --- Fetch stdout from actual job ---
        try:
            stdout_response = awx.get_terraform_plan(actual_job_id)
        except Exception as e:
            logger.exception("Error fetching stdout for job %s: %s", actual_job_id, e)
            return Response({"status": "pending", "detail": "error fetching job stdout"}, status=status.HTTP_202_ACCEPTED)

        # --- Extract stdout text ---
        if isinstance(stdout_response, dict):
            stdout = stdout_response.get("msg", "")
        else:
            stdout = getattr(stdout_response, "text", "") or ""

        logger.info("AWX stdout first 500 chars for job %s:\n%s", actual_job_id, stdout[:500].replace("\n", "\\n"))

        # --- Extract Terraform plan ---
        extracted = None
        begin_marker = "===BEGIN_TERRAFORM_PLAN==="
        end_marker = "===END_TERRAFORM_PLAN==="
        start = stdout.find(begin_marker)
        end = stdout.find(end_marker)

        if start != -1 and end != -1 and end > start:
            extracted = stdout[start + len(begin_marker):end].strip()
            logger.info("Found plan markers for job %s. Extracted length: %d", pk, len(extracted))
        else:
            # fallback regex strategies
            terraform_intro_re = re.compile(
                r"(Terraform used the selected providers[\s\S]+?)(?:Changes to Outputs:|Plan:|\Z)",
                re.IGNORECASE,
            )
            m = terraform_intro_re.search(stdout)
            if m:
                extracted = m.group(0).strip()
                logger.info("Found Terraform provider block for job %s", pk)
            else:
                plan_re = re.compile(r"(Plan:.*?$[\s\S]*)", re.MULTILINE)
                m2 = plan_re.search(stdout)
                if m2:
                    start_idx = max(0, m2.start() - 2000)
                    extracted = stdout[start_idx:].strip()
                    logger.info("Found 'Plan:' section for job %s", pk)

        # --- Save extracted plan if found ---
        if extracted:
            try:
                plan.plan_text = extracted
                if hasattr(plan, "status"):
                    plan.status = "completed"
                plan.save()
                logger.info("Saved Terraform plan for job %s to DB (id=%s)", pk, plan.id)
                return Response({"status": "completed", "plan_text": plan.plan_text}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.exception("Failed to save extracted plan for job %s: %s", pk, e)
                return Response({"error": "failed to save plan"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- Handle failed or still-running jobs ---
        if job_status and str(job_status).lower() in ("failed", "error"):
            plan.plan_text = stdout[:100000]
            if hasattr(plan, "status"):
                plan.status = "failed"
            plan.save()
            logger.info("Job %s failed; saved stdout for debugging", pk)
            return Response({"status": "failed", "plan_text": plan.plan_text}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
