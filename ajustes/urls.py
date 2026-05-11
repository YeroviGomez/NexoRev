from django.urls import path

from . import views

urlpatterns = [
    path('', views.ajustes_view, name='ajustes'),
]
