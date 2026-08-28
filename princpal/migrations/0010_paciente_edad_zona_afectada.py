from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('princpal', '0009_paciente_doctor_and_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='paciente',
            name='edad',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='edad'),
        ),
        migrations.AddField(
            model_name='paciente',
            name='zona_afectada',
            field=models.CharField(blank=True, max_length=100, verbose_name='zona afectada'),
        ),
    ]
