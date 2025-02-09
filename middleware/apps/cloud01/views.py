from django.shortcuts import render
from rest_framework import viewsets, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import BuildRequest
from .serializers import *
from pprint import pprint
from .awx import AWX
import traceback
from .input_handler import format_awx_request
# Create your views here.

class BuildRequestViewSet(viewsets.ModelViewSet):
    serializer_class = BuildRequestSerializer     
    queryset = BuildRequest.objects.all()

class submitAWXJob(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request, format=None):
        try:
            data = self.request.data
            pprint(data, indent=3)
            job_vars = format_awx_request(data)

    
        #     # Validate job vars
        #     validation = Validator(data)
        #     if validation.errors:
        #         return Response({'error': validation.errors})

            # Format request
            awx_request = {"extra_vars": job_vars}
            pprint(awx_request)

            if awx_request["extra_vars"]["job_vars"]["primary_var_prefix"].lower() == "zzz":
                test_gui = True
            else:
                test_gui = False
        # Post to Ansible 

            awx = AWX()
            request = awx.launch_build(awx_request,test_gui)
        # awx_request['extra_vars']['workflow_id'] = request.json()['workflow_job']
        #     awx_request['extra_vars']['mail_flag'] = 'prepped'

            return Response({'success': 'build successfully raised!'}, status=200)
        except Exception as e:
            print(e)
            return Response({'error': 'Error encountered when submitting request.', 'stacktrace': str(traceback.format_exc())}, status=500)
