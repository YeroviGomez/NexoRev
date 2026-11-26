from django.urls import path

from mensajeria.consumers import MensajeriaConsumer


websocket_urlpatterns = [
    path('ws/mensajeria/', MensajeriaConsumer.as_asgi()),
]
