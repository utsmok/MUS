# Generated by Django 5.0.6 on 2024-06-01 22:17

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mus_wizard", "0002_group_acronym_group_internal_repository_id_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="group",
            index=models.Index(
                fields=["internal_repository_id"], name="mus_wizard__interna_19dcb1_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="group",
            index=models.Index(
                fields=["org_type"], name="mus_wizard__org_typ_e35823_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="group",
            index=models.Index(
                fields=["acronym"], name="mus_wizard__acronym_59c0dd_idx"
            ),
        ),
    ]
