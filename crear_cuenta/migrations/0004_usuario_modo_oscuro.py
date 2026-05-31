# Generated migration for adding modo_oscuro field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crear_cuenta', '0003_usuario_foto'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='modo_oscuro',
            field=models.BooleanField(default=False, verbose_name='modo oscuro'),
        ),
    ]
