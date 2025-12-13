from django.db import models

class BuildRequest(models.Model):
    request_id = models.AutoField(primary_key=True)
    job_data = models.JSONField()
    master_ticket = models.CharField(blank=True, max_length=50)

    class Meta:
        app_label = 'cloud01'  # explicitly assign the app label

    def __str__(self):
        return f"BuildRequest {self.request_id}"


from django.db import models

class InfraOutput(models.Model):
    job_id = models.CharField(max_length=100, db_index=True)  # or run_id
    key = models.CharField(max_length=100)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "cloud01"
        constraints = [
            models.UniqueConstraint(fields=["job_id", "key"], name="uniq_output_per_job_key")
        ]

    def __str__(self):
        return f"{self.job_id} | {self.key}: {self.value}"


class TerraformPlan(models.Model):
    run_id = models.CharField(max_length=255, unique=True, null=True, blank=True) 
    job_id = models.CharField(max_length=50, unique=True)
    plan_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'cloud01'  # explicitly assign the app label

    def __str__(self):
        return f"Terraform Plan for Job {self.job_id}"
 