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
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer
from .models import InfraOutput
from .serializers import InfraOutputSerializer

class InfraOutputViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InfraOutput.objects.all()
    serializer_class = InfraOutputSerializer

class InfraOutputCreate(APIView):
    def post(self, request, *args, **kwargs):
        serializer = InfraOutputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tokens = serializer.validated_data

        response = Response(tokens)
        return response


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
            

            return Response({'success': 'build successfully raised!'}, status=200)
        except Exception as e:
            print(e)
            return Response({'error': 'Error encountered when submitting request.', 'stacktrace': str(traceback.format_exc())}, status=500)
