from django.urls import path

from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('verificar-2fa/', views.verify_2fa_view, name='verify_2fa'),
    path('logout/', views.logout_view, name='logout'),
    path('sesion-no-reconocida/<str:token>/', views.revoke_login_session, name='revoke_login_session'),
    path('recuperar_contraseña/', views.forgot_password_view, name='forgot_password'),
    path('verify-recovery-code/', views.verify_recovery_code, name='verify_recovery_code'),
]
