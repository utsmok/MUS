# Generated by Django 5.0.2 on 2024-03-11 13:53

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0033_alter_viewpaper_options_dbupdate"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dbupdate",
            name="updated_papers",
        ),
        migrations.RemoveField(
            model_name="dbupdate",
            name="updated_pure_entries",
        ),
    ]
