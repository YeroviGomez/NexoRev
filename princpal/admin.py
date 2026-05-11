from django.contrib import admin

from .models import Paciente, Sesion


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'telefono', 'fecha_registro')
    search_fields = ('nombre', 'email', 'telefono')
    list_filter = ('fecha_registro',)


@admin.register(Sesion)
class SesionAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'fecha', 'objetivo', 'activo')
    search_fields = ('paciente__nombre', 'objetivo')
    list_filter = ('activo', 'fecha')
