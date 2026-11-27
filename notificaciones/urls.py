from django.urls import path

from . import views


urlpatterns = [
    path('alertas/', views.alertas_dolor, name='notif_alertas'),
    path('alertas/<int:alerta_id>/vista/', views.marcar_alerta_vista, name='notif_alerta_vista'),
    path('alertas/<int:alerta_id>/atendida/', views.marcar_alerta_atendida, name='notif_alerta_atendida'),
    path('recordatorios/', views.recordatorios_paciente, name='notif_recordatorios'),
    path('reporte-semanal/', views.reporte_semanal, name='notif_reporte_semanal'),
    path('recordatorios/<int:recordatorio_id>/', views.recordatorio_detalle, name='notif_recordatorio'),
    path(
        'recordatorios/<int:recordatorio_id>/activo/',
        views.cambiar_estado_recordatorio,
        name='notif_recordatorio_activo',
    ),
]
