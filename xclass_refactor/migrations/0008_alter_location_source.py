# Generated by Django 5.0.6 on 2024-05-27 18:41

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "xclass_refactor",
            "0007_remove_grant_xclass_refa_openale_e3965f_idx_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="location",
            name="source",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="locations",
                to="xclass_refactor.source",
            ),
        ),
    ]
