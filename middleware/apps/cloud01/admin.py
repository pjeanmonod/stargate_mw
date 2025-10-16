from django.contrib import admin
from .models import BuildRequest, InfraOutput, TerraformPlan

# Register your models here
admin.site.register(BuildRequest)
admin.site.register(InfraOutput)
admin.site.register(TerraformPlan)