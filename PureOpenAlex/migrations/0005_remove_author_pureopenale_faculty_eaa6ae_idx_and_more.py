# Generated by Django 5.0.2 on 2024-02-17 21:32

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0004_author_openalex_url_and_more"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_faculty_eaa6ae_idx",
        ),
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_departm_3c350a_idx",
        ),
        migrations.RemoveField(
            model_name="author",
            name="department",
        ),
        migrations.RemoveField(
            model_name="author",
            name="faculty",
        ),
    ]
