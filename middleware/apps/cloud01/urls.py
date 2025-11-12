from django.urls import include, path
from . import views
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CustomTokenObtainPairView, InfraOutputViewSet, TerraformPlanViewSet

# -----------------------------
# DRF routers
# -----------------------------
router = routers.DefaultRouter()
router.register(r'infra', InfraOutputViewSet, basename='infra')
router.register(r'terraform/plan', TerraformPlanViewSet, basename='terraform-plan')

# -----------------------------
# URL patterns
# -----------------------------
urlpatterns = [
    # Manual paths first
    path("terraform/approve/<str:run_id>/", views.approve_terraform_plan, name="terraform-approve"),
    path("configure/", views.configure.as_view(), name="configure"),
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("terraform/destroy/approve/<str:run_id>/", views.approve_terraform_destroy, name="terraform-destroy-approve"),


    # DRF router paths last
    path("", include(router.urls)),
]

