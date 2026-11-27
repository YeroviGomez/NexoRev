from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('princpal', '0016_session_status_duration_and_treatment_goal'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagnostico',
            name='zona_afectada',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='diagnostico',
            name='respuestas',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='diagnostico',
            name='pregunta1',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='diagnostico',
            name='pregunta2',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='diagnostico',
            name='pregunta3',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
