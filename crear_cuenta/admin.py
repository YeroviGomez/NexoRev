from django.contrib import admin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('email', 'nombre', 'is_active', 'fecha_creacion')
    search_fields = ('email', 'nombre')
    list_filter = ('is_active',)
