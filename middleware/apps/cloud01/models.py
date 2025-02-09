from django.db import models

class BuildRequest(models.Model):

    request_id = models.AutoField(primary_key=True)
    job_data = models.JSONField()
    master_ticket = models.CharField(blank=True, max_length=50)

    class Meta:
        app_label = 'cloud01'
