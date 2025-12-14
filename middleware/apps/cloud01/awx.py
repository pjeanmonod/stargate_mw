import requests
import json
import datetime
import requests
from urllib.parse import urljoin
import logging
logger = logging.getLogger(__name__)


class AWX:
    def __init__(self):
        self.url = 'https://ec2-13-61-132-117.eu-north-1.compute.amazonaws.com/api/v2/'
        self.user = 'admin'
        self.password = 'bob'
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        self.session.verify = False

    def launch_build(self, net_vars):
        URL_FULL = self.url + f"workflow_job_templates/15/launch/"
        return self.session.post(url=URL_FULL, json=net_vars, verify=False)


    def get_terraform_plan(self, job_id):
        """
        Fetch the Terraform plan output (stdout text) for a given AWX job.
        """
        url_full = urljoin(self.url, f"jobs/{job_id}/stdout/?format=txt")
        response = self.session.get(url_full)
        return response

    def approve_workflow(self, job_id):
        """
        Approve the workflow approval node so Terraform apply can proceed.
        """
        approval_id = int(job_id) + 3  # your fixed +3 offset
        url_full = urljoin(self.url, f"workflow_approvals/{approval_id}/approve/")
        response = self.session.post(url_full)
        return response
    
    def approve_destroy_workflow(self, job_id):
        """
        Approve the workflow approval node so Terraform destroy can proceed.
        """
        approval_id = int(job_id) + 5  # destroy node offset (+5)
        url_full = urljoin(self.url, f"workflow_approvals/{approval_id}/approve/")
        response = self.session.post(url_full)
        return response
    
    def get_job(self, job_id):
        """
        Fetch AWX job metadata by ID.
        Returns dict parsed from JSON.
        """
        url_full = urljoin(self.url, f"workflow_jobs/{job_id}/")
        try:
            response = self.session.get(url_full)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception("Failed to fetch job metadata for %s: %s", job_id, e)
            return {}