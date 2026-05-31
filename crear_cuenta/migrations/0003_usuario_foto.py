# Generated migration for adding foto field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crear_cuenta', '0002_usuario_telefono_edad'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='foto',
            field=models.ImageField(blank=True, null=True, upload_to='perfiles/', verbose_name='foto de perfil'),
        ),
    ]
