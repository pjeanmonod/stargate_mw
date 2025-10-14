from .models import TerraformPlan

def save_terraform_plan(job_id, plan_output):
    """
    Saves or updates the Terraform plan text for a given job_id.
    """
    obj, created = TerraformPlan.objects.get_or_create(job_id=job_id)
    obj.plan_text = plan_output
    obj.save()