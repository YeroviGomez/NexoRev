import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('princpal', '0011_diagnostico_usuario'),
    ]

    operations = [
        migrations.AddField(
            model_name='sesion',
            name='realizada',
            field=models.BooleanField(default=False, verbose_name='realizada'),
        ),
        migrations.AddField(
            model_name='sesion',
            name='realizada_en',
            field=models.DateTimeField(blank=True, null=True, verbose_name='realizada el'),
        ),
        migrations.CreateModel(
            name='EvaluacionClinica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True, verbose_name='fecha de evaluación')),
                ('nivel_dolor', models.PositiveSmallIntegerField(
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(10),
                    ],
                    verbose_name='dolor (EVA)',
                )),
                ('metrica', models.CharField(blank=True, max_length=100, verbose_name='métrica clínica')),
                ('valor_actual', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    max_digits=8,
                    null=True,
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name='valor actual',
                )),
                ('unidad', models.CharField(blank=True, max_length=30, verbose_name='unidad')),
                ('paciente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='evaluaciones',
                    to='princpal.paciente',
                )),
            ],
            options={
                'verbose_name': 'Evaluación clínica',
                'verbose_name_plural': 'Evaluaciones clínicas',
                'ordering': ['fecha', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='ObjetivoTerapeutico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=150, verbose_name='objetivo')),
                ('metrica', models.CharField(max_length=100, verbose_name='métrica clínica')),
                ('direccion', models.CharField(
                    choices=[('mayor', 'Alcanzar o superar'), ('menor', 'Reducir hasta')],
                    default='mayor',
                    max_length=10,
                    verbose_name='criterio de cumplimiento',
                )),
                ('valor_objetivo', models.DecimalField(
                    decimal_places=2,
                    max_digits=8,
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name='valor objetivo',
                )),
                ('unidad', models.CharField(blank=True, max_length=30, verbose_name='unidad')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado el')),
                ('paciente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='objetivos',
                    to='princpal.paciente',
                )),
            ],
            options={
                'verbose_name': 'Objetivo terapéutico',
                'verbose_name_plural': 'Objetivos terapéuticos',
                'ordering': ['nombre', 'pk'],
            },
        ),
    ]
