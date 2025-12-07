from .models import TerraformPlan
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def save_terraform_plan(run_id, plan_output):
    """
    Saves or updates the Terraform plan text for a given run_id.
    """
    obj, created = TerraformPlan.objects.get_or_create(run_id=run_id)
    obj.plan_text = plan_output
    obj.save()


def broadcast_job_update(run_id, plan_status, state_status):
    """
    Broadcast a job update to all connected websocket clients.
    """
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "plan_updates",
        {
            "type": "plan_update",  # consumer method name
            "run_id": run_id,
            "plan_status": plan_status,
            "state_status": state_status,
        }
    )
