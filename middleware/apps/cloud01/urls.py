from django.urls import include, path
from . import views
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'buildrequest', views.BuildRequestViewSet, basename='BuildRequest')

urlpatterns = [
    path('', include(router.urls)),
    path('configure', views.submitAWXJob.as_view()),
]
