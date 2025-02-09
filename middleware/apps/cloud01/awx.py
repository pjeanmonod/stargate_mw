import requests
import json
import datetime

class AWX:
    def __init__(self):
        self.url = 'http://10.1.100.90:2222/api/v2/'
        self.user = 'bob'
        self.password = 'bob'
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        self.session.verify = False

    def launch_build(self, net_vars, test_gui):
        # for testing sending data to test workflow
        if test_gui:
            workflow = 11
        else:
            workflow = 10
        URL_FULL = self.url + f"workflow_job_templates/{workflow}/launch/"
        return self.session.post(url=URL_FULL, json=net_vars, verify=False)
