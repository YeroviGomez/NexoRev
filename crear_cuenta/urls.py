from django.urls import path

from . import views

urlpatterns = [
    path('', views.crear_cuenta_view, name='registro'),
]
