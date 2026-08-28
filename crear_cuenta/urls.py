from django.urls import path

from . import views

urlpatterns = [
    path('', views.crear_cuenta_view, name='registro'),
    path('paciente/', views.crear_cuenta_paciente_view, name='registro_paciente'),
    path('doctor/', views.crear_cuenta_doctor_view, name='registro_doctor'),
]
