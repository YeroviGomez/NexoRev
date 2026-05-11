from django.contrib import admin

from .models import LoginAttempt


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('email', 'success', 'timestamp', 'ip_address')
    search_fields = ('email',)
    list_filter = ('success',)
    ordering = ('-timestamp',)
