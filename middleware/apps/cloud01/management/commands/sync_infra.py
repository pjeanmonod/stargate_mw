import subprocess
import json
from django.core.management.base import BaseCommand
from middleware.apps.cloud01.models import InfraOutput

class Command(BaseCommand):
    help = "Sync Terraform outputs into the database"

    def handle(self, *args, **kwargs):
        try:
            # Run terraform output -json
            result = subprocess.run(
                ["terraform", "output", "-json"],
                capture_output=True,
                text=True,
                check=True,
            )
            outputs = json.loads(result.stdout)

            for key, details in outputs.items():
                value = details.get("value")
                InfraOutput.objects.update_or_create(
                    key=key,
                    defaults={"value": value},
                )
                self.stdout.write(self.style.SUCCESS(f"Synced {key}"))

        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f"Terraform command failed: {e.stderr}"))
