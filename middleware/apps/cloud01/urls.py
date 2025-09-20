from django.urls import include, path
from . import views
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CustomTokenObtainPairView

router = routers.DefaultRouter()
# router.register(r'buildrequest', views.BuildRequestViewSet, basename='BuildRequest')

urlpatterns = [
    path('', include(router.urls)),
    path('configure', views.configure.as_view()),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
