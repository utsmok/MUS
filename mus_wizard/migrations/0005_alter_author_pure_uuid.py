# Generated by Django 5.0.6 on 2024-06-10 21:48

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mus_wizard", "0004_author_internal_repository_id_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="author",
            name="pure_uuid",
            field=models.UUIDField(default=None, null=True),
        ),
    ]
