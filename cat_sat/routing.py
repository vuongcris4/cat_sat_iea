from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/optimization/log', consumers.ChatConsumer.as_asgi()),
]
