from django.urls import include, path
from . import views
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CustomTokenObtainPairView, InfraOutputViewSet, TerraformPlanViewSet

router = routers.DefaultRouter()
# router.register(r'buildrequest', views.BuildRequestViewSet, basename='BuildRequest')
router.register(r'infra', InfraOutputViewSet, basename='infra')
router.register(r'terraform/plan', TerraformPlanViewSet, basename='terraform-plan')


urlpatterns = [
    path('', include(router.urls)),
    path('configure', views.configure.as_view()),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("terraform/approve/<uuid:job_id>/", views.approve_terraform_plan, name="terraform-approve"),
]

