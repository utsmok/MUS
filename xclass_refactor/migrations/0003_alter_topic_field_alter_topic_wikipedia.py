# Generated by Django 5.0.6 on 2024-05-18 22:42

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("xclass_refactor", "0002_alter_affiliation_years_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="topic",
            name="field",
            field=models.CharField(
                choices=[
                    ("Medicine", "Medicine"),
                    ("Social Sciences", "Social Sciences"),
                    ("Engineering", "Engineering"),
                    ("Arts and Humanities", "Arts And Humanities"),
                    ("Computer Science", "Computer Science"),
                    (
                        "Biochemistry, Genetics and Molecular Biology",
                        "Biochemistry Genetics And Molecular Biology",
                    ),
                    (
                        "Agricultural and Biological Sciences",
                        "Agricultural And Biological Sciences",
                    ),
                    ("Environmental Science", "Environmental Science"),
                    ("Physics and Astronomy", "Physics And Astronomy"),
                    (
                        "Business, Management and Accounting",
                        "Business Management And Accounting",
                    ),
                    ("Materials Science", "Materials Science"),
                    (
                        "Economics, Econometrics and Finance",
                        "Economics Econometrics And Finance",
                    ),
                    ("Health Professions", "Health Professions"),
                    ("Psychology", "Psychology"),
                    ("Chemistry", "Chemistry"),
                    ("Earth and Planetary Sciences", "Earth And Planetary Sciences"),
                    ("Neuroscience", "Neuroscience"),
                    ("Mathematics", "Mathematics"),
                    ("Immunology and Microbiology", "Immunology And Microbiology"),
                    ("Decision Sciences", "Decision Sciences"),
                    ("Energy", "Energy"),
                    ("Nursing", "Nursing"),
                    (
                        "Pharmacology, Toxicology and Pharmaceutics",
                        "Pharmacology Toxicology And Pharmaceuticals",
                    ),
                    ("Dentistry", "Dentistry"),
                    ("Chemical Engineering", "Chemical Engineering"),
                ]
            ),
        ),
        migrations.AlterField(
            model_name="topic",
            name="wikipedia",
            field=models.URLField(),
        ),
    ]
