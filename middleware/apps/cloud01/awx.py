import requests
import json
import datetime

class AWX:
    def __init__(self):
        self.url = 'https://ec2-51-20-95-48.eu-north-1.compute.amazonaws.com/api/v2'
        self.user = 'admin'
        self.password = 'bob'
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        self.session.verify = False

    def launch_build(self, net_vars):
        # for testing sending data to test workflow
        URL_FULL = self.url + f"workflow_job_templates/11/launch/"
        return self.session.post(url=URL_FULL, json=net_vars, verify=False)
