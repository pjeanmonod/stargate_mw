# cloud01/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import TerraformPlan, InfraOutput

channel_layer = get_channel_layer()

@receiver(post_save, sender=TerraformPlan)
def broadcast_plan_update(sender, instance, **kwargs):
    data = {
        "type": "plan_update",
        "id": instance.job_id,
        "plan_status": getattr(instance, "plan_status", "unknown"),
        "plan_output": instance.plan_text or "",
    }
    async_to_sync(channel_layer.group_send)(
        "plan_updates",  # matches your consumers.py group
        {
            "type": "plan_update",  # must match method name in consumer
            **data,
        }
    )

@receiver(post_save, sender=InfraOutput)
def broadcast_state_update(sender, instance, **kwargs):
    data = {
        "type": "plan_update",  # reuse same event type for frontend
        "id": instance.key,
        "state_status": getattr(instance, "state_status", "unknown"),
        "state_output": instance.value or {},
    }
    async_to_sync(channel_layer.group_send)(
        "plan_updates",
        {
            "type": "plan_update",
            **data,
        }
    )
