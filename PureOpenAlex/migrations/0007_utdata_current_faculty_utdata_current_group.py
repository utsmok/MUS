# Generated by Django 5.0.2 on 2024-02-17 21:33

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0006_rename_job_title_utdata_current_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="utdata",
            name="current_faculty",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="utdata",
            name="current_group",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
    ]
