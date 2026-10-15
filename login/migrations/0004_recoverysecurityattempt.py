from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('login', '0003_twofactorcode'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecoverySecurityAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254, verbose_name='correo electrónico')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='dirección IP')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='fecha')),
            ],
            options={
                'verbose_name': 'Intento de recuperación de cuenta',
                'verbose_name_plural': 'Intentos de recuperación de cuenta',
                'ordering': ['-timestamp'],
            },
        ),
    ]
