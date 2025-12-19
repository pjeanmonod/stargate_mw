# cloud01/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import TerraformPlan, InfraOutput

channel_layer = get_channel_layer()

@receiver(post_save, sender=TerraformPlan)
def broadcast_plan_update(sender, instance, **kwargs):
    event = {
        "event": "plan_update",
        "run_id": str(instance.run_id),      
        "job_id": str(instance.job_id),      
    }

    if instance.plan_text:
        event["plan_output"] = instance.plan_text
        event["plan_status"] = "ready"

    async_to_sync(channel_layer.group_send)(
        "plan_updates",
        {"type": "plan_update", **event},
    )

@receiver(post_save, sender=InfraOutput)
def broadcast_state_update(sender, instance, **kwargs):
    event = {
        "event": "state_update",       
        "run_id": instance.job_id,      
        "key": instance.key,
        "state_status": "ready",
        "state_output": instance.value or {},
        "state_updated_at": instance.updated_at.isoformat(), 
    }

    async_to_sync(channel_layer.group_send)(
        "plan_updates",
        {"type": "plan_update", **event},   
    )
