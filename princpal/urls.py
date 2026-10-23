from django.urls import path

from . import views

urlpatterns = [
    path('', views.principal_view, name='principal'),
    path('api/session-status/', views.session_status_api, name='session_status_api'),
    path('pacientes/agregar/', views.add_paciente_view, name='agregar_paciente'),
    path('medicos/<int:doctor_id>/pacientes/', views.doctor_patients_api, name='doctor_patients_api'),
    path('pacientes/<int:paciente_id>/', views.paciente_detail_api, name='paciente_detail_api'),
    path('api/medico/dashboard/', views.doctor_dashboard_data_api, name='doctor_dashboard_data'),
    path('api/paciente/progreso/', views.patient_progress_data_api, name='patient_progress_data'),
    path('pacientes/<int:paciente_id>/evaluaciones/', views.register_clinical_evaluation, name='register_clinical_evaluation'),
    path('pacientes/<int:paciente_id>/objetivos/', views.add_therapeutic_goal, name='add_therapeutic_goal'),
    path('pacientes/<int:paciente_id>/sesiones/', views.schedule_session, name='schedule_session'),
    path('pacientes/<int:paciente_id>/rutinas/', views.assign_routine_view, name='assign_routine'),
    path('sesiones/<int:sesion_id>/completar/', views.complete_session, name='complete_session'),
    path('pacientes/<int:paciente_id>/sesiones/<int:sesion_id>/reagendar/', views.reschedule_session_view, name='reschedule_session'),
    path('sesiones/<int:sesion_id>/solicitar-reagendamiento/', views.create_reschedule_request, name='create_reschedule_request'),
    path('solicitudes-reagendamiento/<int:solicitud_id>/revisar/', views.review_reschedule_request, name='review_reschedule_request'),
    path('solicitudes-reagendamiento/<int:solicitud_id>/responder/', views.respond_to_reschedule_proposal, name='respond_to_reschedule_proposal'),
    path('videos/<int:video_index>/', views.video_detail_view, name='video_detail'),
    path('videos/<int:video_index>/complete/', views.complete_video_view, name='complete_video'),
    path('api/videos/page/', views.videos_page_view, name='videos_page'),
    path('api/history/', views.history_view, name='history'),
    path('api/videos/surprise/', views.surprise_video_view, name='surprise_video'),
    path('api/update-profile/', views.update_profile_view, name='update_profile'),
    path('api/update-appearance-preference/', views.update_appearance_preference, name='update_appearance_preference'),
    path('api/change-password/', views.change_password_view, name='change_password'),
    path('api/security-questions/', views.update_security_questions, name='update_security_questions'),
    path('api/upload-photo/', views.upload_profile_photo, name='upload_profile_photo'),
    path('api/reset-photo/', views.reset_profile_photo, name='reset_profile_photo'),
    path('api/upload-video/', views.upload_video_view, name='upload_video'),
]
