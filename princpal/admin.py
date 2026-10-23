from django.contrib import admin

from .models import (
    EjercicioPlantillaRutina,
    EjercicioRutinaAsignada,
    EvaluacionClinica,
    ObjetivoTerapeutico,
    OcurrenciaRutina,
    Paciente,
    PlantillaRutina,
    RutinaAsignada,
    Sesion,
)


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'telefono', 'fecha_registro')
    search_fields = ('nombre', 'email', 'telefono')
    list_filter = ('fecha_registro',)


@admin.register(Sesion)
class SesionAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'fecha', 'duracion_minutos', 'objetivo', 'estado')
    search_fields = ('paciente__nombre', 'objetivo')
    list_filter = ('estado', 'fecha')


@admin.register(EvaluacionClinica)
class EvaluacionClinicaAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'fecha', 'nivel_dolor', 'metrica', 'valor_actual')
    search_fields = ('paciente__nombre', 'metrica')
    list_filter = ('fecha', 'nivel_dolor')


@admin.register(ObjetivoTerapeutico)
class ObjetivoTerapeuticoAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'nombre', 'metrica', 'valor_objetivo', 'unidad')
    search_fields = ('paciente__nombre', 'nombre', 'metrica')


@admin.register(RutinaAsignada)
class RutinaAsignadaAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'titulo', 'fecha_programada', 'completada_en')
    search_fields = ('paciente__nombre', 'titulo')
    list_filter = ('fecha_programada', 'completada_en')


admin.site.register(PlantillaRutina)
admin.site.register(EjercicioPlantillaRutina)
admin.site.register(EjercicioRutinaAsignada)
admin.site.register(OcurrenciaRutina)
