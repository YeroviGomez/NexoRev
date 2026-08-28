from django.urls import path

from . import views

urlpatterns = [
    path('', views.principal_view, name='principal'),
    path('pacientes/agregar/', views.add_paciente_view, name='agregar_paciente'),
    path('medicos/<int:doctor_id>/pacientes/', views.doctor_patients_api, name='doctor_patients_api'),
    path('pacientes/<int:paciente_id>/', views.paciente_detail_api, name='paciente_detail_api'),
    path('videos/<int:video_index>/', views.video_detail_view, name='video_detail'),
    path('videos/<int:video_index>/complete/', views.complete_video_view, name='complete_video'),
    path('api/videos/page/', views.videos_page_view, name='videos_page'),
    path('api/history/', views.history_view, name='history'),
    path('api/videos/surprise/', views.surprise_video_view, name='surprise_video'),
    path('api/upload-photo/', views.upload_profile_photo, name='upload_profile_photo'),
    path('api/upload-video/', views.upload_video_view, name='upload_video'),
]
