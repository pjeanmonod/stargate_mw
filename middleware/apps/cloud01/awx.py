import requests
import json
import datetime
import requests
from urllib.parse import urljoin

class AWX:
    def __init__(self):
        self.url = 'https://ec2-13-61-132-117.eu-north-1.compute.amazonaws.com/api/v2/'
        self.user = 'admin'
        self.password = 'bob'
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        self.session.verify = False

    def launch_build(self, net_vars):
        # for testing sending data to test workflow
        URL_FULL = self.url + f"workflow_job_templates/11/launch/"
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
        Approve the workflow job so Terraform apply can proceed.
        """
        url_full = urljoin(self.url, f"workflow_jobs/{job_id}/approve/")
        response = self.session.post(url_full)
        return response