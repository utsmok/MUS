# Generated by Django 5.0.2 on 2024-02-26 09:45

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0022_affiliation_remove_author_afas_data_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="journal",
            old_name="doaj",
            new_name="is_in_doaj",
        ),
    ]
