from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crear_cuenta', '0003_usuario_modo_oscuro'),
        ('princpal', '0008_video_hls_manifest'),
    ]

    operations = [
        migrations.AddField(
            model_name='paciente',
            name='usuario',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='perfil_paciente', to='crear_cuenta.usuario', verbose_name='usuario'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='doctor',
            field=models.ForeignKey(blank=True, db_column='doctor_id', limit_choices_to={'role': 'doctor'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pacientes_asignados', to='crear_cuenta.usuario', verbose_name='doctor'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='avance',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='avance (%)'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='estado',
            field=models.CharField(choices=[('inicial', 'Inicial'), ('en_proceso', 'En proceso'), ('avanzado', 'Avanzado'), ('finalizado', 'Finalizado')], default='inicial', max_length=20, verbose_name='estado'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='historial_avance',
            field=models.JSONField(blank=True, default=list, verbose_name='historial de avance'),
        ),
    ]
