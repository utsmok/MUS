# Generated by Django 5.0.2 on 2024-03-05 15:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0025_pureentry_journal_pureentry_keywords"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="location",
            options={},
        ),
        migrations.AlterModelOptions(
            name="pureentry",
            options={},
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_openale_52b0b8_idx",
        ),
        migrations.AddIndex(
            model_name="affiliation",
            index=models.Index(
                fields=["author", "organization"], name="PureOpenAle_author__6774e6_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="location",
            index=models.Index(
                fields=["source", "is_oa", "landing_page_url", "pdf_url"],
                name="PureOpenAle_source__d34842_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="pureentry",
            index=models.Index(
                fields=[
                    "title",
                    "doi",
                    "isbn",
                    "researchutwente",
                    "risutwente",
                    "scopus",
                    "publisher",
                    "date",
                    "paper",
                    "journal",
                ],
                name="PureOpenAle_title_bd5a33_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="source",
            index=models.Index(
                fields=[
                    "openalex_url",
                    "homepage_url",
                    "display_name",
                    "issn",
                    "e_issn",
                    "host_org",
                ],
                name="PureOpenAle_openale_934997_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="utdata",
            index=models.Index(
                fields=[
                    "employee",
                    "current_position",
                    "current_group",
                    "current_faculty",
                ],
                name="PureOpenAle_employe_469278_idx",
            ),
        ),
    ]
