# Generated by Django 5.0.2 on 2024-03-13 15:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0035_alter_paper_title_alter_pilotpuredata_title_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paper",
            name="pdf_link_primary",
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AlterField(
            model_name="paper",
            name="primary_link",
            field=models.CharField(max_length=1024),
        ),
    ]
