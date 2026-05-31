# Generated migration for adding telefono and edad fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crear_cuenta', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='telefono',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='teléfono'),
        ),
        migrations.AddField(
            model_name='usuario',
            name='edad',
            field=models.IntegerField(blank=True, null=True, verbose_name='edad'),
        ),
    ]
