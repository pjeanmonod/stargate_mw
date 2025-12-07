"""
ASGI config for middleware project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""


import os

from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

from middleware.apps.cloud01 import routing as cloud01_routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware.settings")

# standard Django ASGI app
django_asgi_app = get_asgi_application()

# channels protocol router
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            cloud01_routing.websocket_urlpatterns
        )
    ),
})
