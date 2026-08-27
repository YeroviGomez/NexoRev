from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('princpal', '0007_video_thumbnail'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='hls_manifest',
            field=models.CharField(blank=True, max_length=255, verbose_name='manifiesto HLS'),
        ),
    ]