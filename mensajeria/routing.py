from django.urls import path

from mensajeria.consumers import MensajeriaConsumer
from mensajeria.videollamada import VideollamadaConsumer


websocket_urlpatterns = [
    path('ws/mensajeria/', MensajeriaConsumer.as_asgi()),
    path('ws/videollamada/', VideollamadaConsumer.as_asgi()),
]
