# Generated by Django 5.0.2 on 2024-04-05 22:48

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0042_paper_calc_taverne_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="utdata",
            name="pure_uuid",
            field=models.UUIDField(default=None, null=True, unique=True),
        ),
    ]