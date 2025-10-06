from django.urls import include, path
from . import views
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CustomTokenObtainPairView, InfraOutputViewSet
import views

router = routers.DefaultRouter()
# router.register(r'buildrequest', views.BuildRequestViewSet, basename='BuildRequest')
router.register(r'infra', InfraOutputViewSet, basename='infra')


urlpatterns = [
    path('', include(router.urls)),
    path('configure', views.configure.as_view()),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

