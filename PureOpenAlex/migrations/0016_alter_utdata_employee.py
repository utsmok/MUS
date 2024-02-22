# Generated by Django 5.0.2 on 2024-02-20 10:12

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0015_paper_pureopenale_id_4a0282_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="utdata",
            name="employee",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="utdata",
                to="PureOpenAlex.author",
            ),
        ),
    ]
