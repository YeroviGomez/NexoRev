import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('princpal', '0017_asignacionmedico'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='asignacionmedico',
            old_name='creada_por',
            new_name='creada_por_medico',
        ),
        migrations.RenameField(
            model_name='asignacionmedico',
            old_name='creada_por_admin',
            new_name='creada_por',
        ),
        migrations.AlterField(
            model_name='asignacionmedico',
            name='creada_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asignaciones_creadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='asignacionmedico',
            name='creada_por_medico',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asignaciones_medicas_iniciales_creadas',
                to='crear_cuenta.usuario',
            ),
        ),
    ]
