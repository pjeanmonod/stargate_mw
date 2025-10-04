from django.db import models

class BuildRequest(models.Model):

    request_id = models.AutoField(primary_key=True)
    job_data = models.JSONField()
    master_ticket = models.CharField(blank=True, max_length=50)

    class Meta:
        app_label = 'cloud01'

class InfraOutput(models.Model):
    key = models.CharField(max_length=100, unique=True)   # Terraform output key
    value = models.JSONField()                            # Flexible JSON storage
    updated_at = models.DateTimeField(auto_now=True)      # Timestamp

    class Meta:
        app_label = 'cloud01'

def __str__(self):
        return f"{self.key}: {self.value}"