from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crear_cuenta', '0005_usuario_desactivar_animaciones_usuario_tamano_letra'),
    ]

    operations = [
        migrations.CreateModel(
            name='SecurityQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.CharField(max_length=255, verbose_name='pregunta de seguridad')),
                ('question_key', models.CharField(max_length=255, verbose_name='pregunta normalizada')),
                ('answer_hash', models.CharField(max_length=128, verbose_name='hash de respuesta')),
                ('is_custom', models.BooleanField(default=False, verbose_name='pregunta personalizada')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='fecha de creación')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='security_questions',
                    to='crear_cuenta.usuario',
                )),
            ],
            options={
                'verbose_name': 'Pregunta de seguridad',
                'verbose_name_plural': 'Preguntas de seguridad',
                'ordering': ['pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='securityquestion',
            constraint=models.UniqueConstraint(
                fields=('user', 'question_key'),
                name='unique_security_question_per_user',
            ),
        ),
    ]
