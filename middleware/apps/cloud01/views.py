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


class configure(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request, format=None):
        try:
            # extract data from incoming request
            data = self.request.data
            pprint(data, indent=3)
            job_vars = format_awx_request(data)

            # Format request data for sending to Ansible AWX
            # job_vars = (data)
            awx_request = {"extra_vars": job_vars}
            pprint(awx_request)


            # Post data to Ansible AWX
            awx = AWX()
            request = awx.launch_build(awx_request)
            pprint(request)

            return Response({'success': 'build successfully raised!'}, status=200)
        except Exception as e:
            print(e)
            return Response({'error': 'Error encountered when submitting request.', 'stacktrace': str(traceback.format_exc())}, status=500)
