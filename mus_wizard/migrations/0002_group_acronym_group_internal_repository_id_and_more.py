# Generated by Django 5.0.6 on 2024-06-01 22:04

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mus_wizard", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="acronym",
            field=models.CharField(null=True),
        ),
        migrations.AddField(
            model_name="group",
            name="internal_repository_id",
            field=models.CharField(null=True),
        ),
        migrations.AddField(
            model_name="group",
            name="org_type",
            field=models.CharField(null=True),
        ),
        migrations.AddField(
            model_name="group",
            name="part_of",
            field=models.ManyToManyField(
                related_name="subgroups", to="mus_wizard.group"
            ),
        ),
        migrations.AddField(
            model_name="group",
            name="scopus_affiliation_ids",
            field=models.JSONField(
                encoder=django.core.serializers.json.DjangoJSONEncoder, null=True
            ),
        ),
        migrations.AlterField(
            model_name="group",
            name="faculty",
            field=models.CharField(null=True),
        ),
    ]
