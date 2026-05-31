from django.urls import path

from . import views

urlpatterns = [
    path('', views.principal_view, name='principal'),
    path('api/update-profile/', views.update_profile, name='update_profile'),
    path('api/change-password/', views.change_password, name='change_password'),
    path('api/upload-photo/', views.upload_profile_photo, name='upload_photo'),
    path('api/toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
]
