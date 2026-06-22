import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'azul_game.settings')

import azul.routing  # noqa: E402

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(azul.routing.websocket_urlpatterns),
})
