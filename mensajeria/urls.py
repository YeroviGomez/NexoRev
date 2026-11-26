from django.urls import path

from mensajeria import views


app_name = 'mensajeria'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('api/conversaciones/', views.lista_conversaciones, name='conversaciones'),
    path(
        'api/pacientes/<int:paciente_id>/mensajes/',
        views.historial_mensajes,
        name='historial',
    ),
    path(
        'api/pacientes/<int:paciente_id>/leidos/',
        views.marcar_leidos,
        name='marcar_leidos',
    ),
    path('api/no-leidos/', views.contador_no_leidos, name='no_leidos'),
]
