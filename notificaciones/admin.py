from django.contrib import admin

from .models import AlertaDolor


@admin.register(AlertaDolor)
class AlertaDolorAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'doctor', 'nivel_dolor', 'regla', 'estado', 'creada_en')
    list_filter = ('estado', 'regla', 'creada_en')
    search_fields = ('paciente__nombre', 'paciente__email', 'doctor__nombre', 'doctor__email')
