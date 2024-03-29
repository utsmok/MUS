# Generated by Django 5.0.2 on 2024-03-08 20:54

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "PureOpenAlex",
            "0030_alter_author_options_alter_organization_options_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="journal",
            name="dealdata",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="PureOpenAlex.dealdata",
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="PureOpenAlex.source",
            ),
        ),
        migrations.AlterField(
            model_name="paper",
            name="journal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="papers",
                to="PureOpenAlex.journal",
            ),
        ),
        migrations.AlterField(
            model_name="pureentry",
            name="journal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="pure_entries",
                to="PureOpenAlex.journal",
            ),
        ),
        migrations.AlterField(
            model_name="pureentry",
            name="paper",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pure_entries",
                to="PureOpenAlex.paper",
            ),
        ),
    ]
