# Generated by Django 5.0.2 on 2024-02-22 23:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0020_alter_author_afas_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="pureentry",
            name="authors",
            field=models.ManyToManyField(
                related_name="pure_entries", to="PureOpenAlex.author"
            ),
        ),
    ]
