from django.db import models

class BuildRequest(models.Model):
    request_id = models.AutoField(primary_key=True)
    job_data = models.JSONField()
    master_ticket = models.CharField(blank=True, max_length=50)

    class Meta:
        app_label = 'cloud01'  # explicitly assign the app label

    def __str__(self):
        return f"BuildRequest {self.request_id}"


class InfraOutput(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'cloud01'  # explicitly assign the app label

    def __str__(self):
        return f"{self.key}: {self.value}"


class TerraformPlan(models.Model):
    run_id = models.CharField(max_length=255, unique=True) 
    job_id = models.CharField(max_length=50, unique=True)
    plan_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'cloud01'  # explicitly assign the app label

    def __str__(self):
        return f"Terraform Plan for Job {self.job_id}"
 