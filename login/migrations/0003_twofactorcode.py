from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('login', '0002_passwordrecovery'),
    ]

    operations = [
        migrations.CreateModel(
            name='TwoFactorCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, verbose_name='correo electrónico')),
                ('code', models.CharField(max_length=6, verbose_name='código')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='fecha de creación')),
                ('attempts', models.PositiveSmallIntegerField(default=0, verbose_name='intentos')),
                ('is_used', models.BooleanField(default=False, verbose_name='utilizado')),
            ],
            options={
                'verbose_name': 'Código de autenticación en dos pasos',
                'verbose_name_plural': 'Códigos de autenticación en dos pasos',
                'ordering': ['-created_at'],
            },
        ),
    ]