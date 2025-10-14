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

        # --- Ensure DB row exists ---
        try:
            plan, created = TerraformPlan.objects.get_or_create(job_id=pk)
            if created:
                logger.info("Created placeholder TerraformPlan DB row for job %s", pk)
        except Exception as e:
            logger.exception("DB error getting/creating TerraformPlan for job %s: %s", pk, e)
            return Response({"error": "DB error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- Return immediately if plan already exists ---
        if plan.plan_text:
            logger.info("Plan already present in DB for job %s (id=%s), returning", pk, plan.id)
            return Response({"status": "completed", "plan_text": plan.plan_text}, status=status.HTTP_200_OK)

        awx = AWX()
        stdout = ""
        actual_job_id = pk
        job_status = None

        # --- Fetch job metadata ---
        try:
            job_meta = awx.get_job(pk)
        except Exception as e:
            logger.exception("Error fetching job metadata for job %s: %s", pk, e)
            return Response({"status": "pending", "detail": "error fetching job metadata"}, status=status.HTTP_202_ACCEPTED)

        # --- Handle workflow jobs: find Stage/terraform child job ---
        if job_meta.get("type") == "workflow_job":
            terraform_node = None
            STAGE_NODE_TEMPLATE_ID = 767

            try:
                # 1️⃣ Lookup by static template node ID
                nodes_url = f"{awx.url}/api/v2/workflow_jobs/{pk}/workflow_nodes/?workflow_job_template_node={STAGE_NODE_TEMPLATE_ID}"
                logger.info("Attempting Stage node lookup by template ID %s for workflow %s", STAGE_NODE_TEMPLATE_ID, pk)

                resp = awx.session.get(nodes_url, auth=awx.auth, verify=False)
                resp.raise_for_status()
                results = resp.json().get("results", [])

                if results:
                    node = results[0]
                    job = node.get("summary_fields", {}).get("job")
                    if job and job.get("id"):
                        terraform_node = job
                        logger.info("Found Stage child job %s via template node %s", job["id"], STAGE_NODE_TEMPLATE_ID)

                # 2️⃣ Fallback: search by name if template ID lookup failed
                if not terraform_node:
                    logger.warning("Direct Stage node lookup failed — falling back to name search")
                    nodes_url = f"{awx.url}/api/v2/workflow_jobs/{pk}/workflow_nodes/"
                    nodes_resp = awx.session.get(nodes_url, auth=awx.auth, verify=False)
                    nodes_resp.raise_for_status()
                    nodes = nodes_resp.json().get("results", [])

                    for node in nodes:
                        node_job = node.get("summary_fields", {}).get("job")
                        if node_job and any(k in node_job.get("name", "").lower() for k in ["stage", "terraform"]):
                            terraform_node = node_job
                            logger.info("Found Stage child job %s via name search", node_job["id"])
                            break

                # 3️⃣ Finalize which job to fetch stdout from
                if terraform_node:
                    actual_job_id = terraform_node["id"]
                    job_status = terraform_node.get("status")
                    logger.info("Resolved actual Terraform/Stage job ID %s for workflow %s", actual_job_id, pk)
                else:
                    logger.warning("No Stage/Terraform node found for workflow job %s; using workflow stdout fallback", pk)
                    job_status = job_meta.get("status")

            except Exception as e:
                logger.exception("Error traversing workflow nodes for job %s: %s", pk, e)
                job_status = job_meta.get("status")

        else:
            # Not a workflow job — pull job_status directly
            job_status = job_meta.get("status")

        # --- Fetch stdout from actual job ---
        try:
            stdout_response = awx.get_terraform_plan(actual_job_id)
            if isinstance(stdout_response, dict):
                stdout = stdout_response.get("msg", "")
            else:
                stdout = getattr(stdout_response, "text", "") or ""
            logger.info("AWX stdout first 500 chars for job %s:\n%s", actual_job_id, stdout[:500].replace("\n", "\\n"))
        except Exception as e:
            logger.exception("Error fetching stdout for job %s: %s", actual_job_id, e)
            return Response({"status": "pending", "detail": "error fetching job stdout"}, status=status.HTTP_202_ACCEPTED)

        # --- Extract Terraform plan ---
        extracted = None
        begin_marker = "===BEGIN_TERRAFORM_PLAN==="
        end_marker = "===END_TERRAFORM_PLAN==="
        start = stdout.find(begin_marker)
        end = stdout.find(end_marker)

        if start != -1 and end != -1 and end > start:
            extracted = stdout[start + len(begin_marker):end].strip()
        else:
            # fallback regex strategies
            terraform_intro_re = re.compile(r"(Terraform used the selected providers[\s\S]+?)(?:Changes to Outputs:|Plan:|\Z)", re.IGNORECASE)
            m = terraform_intro_re.search(stdout)
            if m:
                extracted = m.group(0).strip()
            else:
                plan_re = re.compile(r"(Plan:.*?$[\s\S]*)", re.MULTILINE)
                m2 = plan_re.search(stdout)
                if m2:
                    start_idx = max(0, m2.start() - 2000)
                    extracted = stdout[start_idx:].strip()

        # --- Save plan if extracted ---
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

        # --- Handle failed or running jobs ---
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
