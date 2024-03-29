# Generated by Django 5.0.2 on 2024-02-25 23:02

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("PureOpenAlex", "0021_pureentry_authors"),
    ]

    operations = [
        migrations.CreateModel(
            name="Affiliation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("years", models.JSONField(default=dict)),
            ],
        ),
        migrations.RemoveField(
            model_name="author",
            name="afas_data",
        ),
        migrations.RemoveField(
            model_name="journal",
            name="keywords",
        ),
        migrations.RemoveField(
            model_name="paper",
            name="keywords",
        ),
        migrations.AlterModelOptions(
            name="author",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="dealdata",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="location",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="paper",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="pureauthor",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="pureentry",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="source",
            options={"get_latest_by": "modified"},
        ),
        migrations.AlterModelOptions(
            name="viewpaper",
            options={"get_latest_by": "modified"},
        ),
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_name_762328_idx",
        ),
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_is_ut_2714be_idx",
        ),
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_orcid_ba75ad_idx",
        ),
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_afas_da_3bf8c4_idx",
        ),
        migrations.RemoveIndex(
            model_name="author",
            name="PureOpenAle_openale_479667_idx",
        ),
        migrations.RemoveIndex(
            model_name="authorship",
            name="PureOpenAle_author__751201_idx",
        ),
        migrations.RemoveIndex(
            model_name="authorship",
            name="PureOpenAle_paper_i_421339_idx",
        ),
        migrations.RemoveIndex(
            model_name="authorship",
            name="PureOpenAle_corresp_0ca0c7_idx",
        ),
        migrations.RemoveIndex(
            model_name="dealdata",
            name="PureOpenAle_publish_fadc55_idx",
        ),
        migrations.RemoveIndex(
            model_name="dealdata",
            name="PureOpenAle_deal_st_c790ea_idx",
        ),
        migrations.RemoveIndex(
            model_name="dealdata",
            name="PureOpenAle_oa_type_f36d66_idx",
        ),
        migrations.RemoveIndex(
            model_name="journal",
            name="PureOpenAle_name_74a975_idx",
        ),
        migrations.RemoveIndex(
            model_name="journal",
            name="PureOpenAle_doaj_17a910_idx",
        ),
        migrations.RemoveIndex(
            model_name="journal",
            name="PureOpenAle_is_oa_bc75ad_idx",
        ),
        migrations.RemoveIndex(
            model_name="journal",
            name="PureOpenAle_publish_68d2fc_idx",
        ),
        migrations.RemoveIndex(
            model_name="location",
            name="PureOpenAle_source__b23ba4_idx",
        ),
        migrations.RemoveIndex(
            model_name="location",
            name="PureOpenAle_is_prim_6c957d_idx",
        ),
        migrations.RemoveIndex(
            model_name="location",
            name="PureOpenAle_is_best_5ea653_idx",
        ),
        migrations.RemoveIndex(
            model_name="location",
            name="PureOpenAle_is_oa_376bf2_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_doi_4e4bfb_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_title_7fb604_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_is_in_p_b77ca0_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_has_pur_a0fb2c_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_year_73ca8c_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_is_oa_bda7e8_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_openacc_eb4682_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_taverne_489dc3_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_itemtyp_60b962_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_license_a86452_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_ut_keyw_9514e2_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_id_4a0282_idx",
        ),
        migrations.RemoveIndex(
            model_name="paper",
            name="PureOpenAle_openale_f89e2c_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureauthor",
            name="PureOpenAle_name_d174b7_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureauthor",
            name="PureOpenAle_author__a4ac4e_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureentry",
            name="PureOpenAle_title_f31254_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureentry",
            name="PureOpenAle_paper_i_bc1157_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureentry",
            name="PureOpenAle_year_1bc54e_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureentry",
            name="PureOpenAle_ut_keyw_cdb70a_idx",
        ),
        migrations.RemoveIndex(
            model_name="pureentry",
            name="PureOpenAle_itemtyp_b3fade_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_display_820e94_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_host_or_0048cf_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_type_f9b143_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_is_in_d_41b7e4_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_issn_9e1a7d_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_e_issn_565b12_idx",
        ),
        migrations.RemoveIndex(
            model_name="source",
            name="PureOpenAle_openale_b59db0_idx",
        ),
        migrations.RemoveIndex(
            model_name="utdata",
            name="PureOpenAle_employe_58b71d_idx",
        ),
        migrations.RemoveIndex(
            model_name="utdata",
            name="PureOpenAle_avatar_642117_idx",
        ),
        migrations.RemoveIndex(
            model_name="utdata",
            name="PureOpenAle_current_5feba7_idx",
        ),
        migrations.RemoveIndex(
            model_name="utdata",
            name="PureOpenAle_current_4fb84e_idx",
        ),
        migrations.RemoveIndex(
            model_name="utdata",
            name="PureOpenAle_current_082088_idx",
        ),
        migrations.RemoveIndex(
            model_name="viewpaper",
            name="PureOpenAle_display_ee09cc_idx",
        ),
        migrations.RemoveIndex(
            model_name="viewpaper",
            name="PureOpenAle_user_id_54c401_idx",
        ),
        migrations.RemoveField(
            model_name="author",
            name="affiliations",
        ),
        migrations.RemoveField(
            model_name="authorship",
            name="author_article_affiliation",
        ),
        migrations.RemoveField(
            model_name="authorship",
            name="author_article_name",
        ),
        migrations.RemoveField(
            model_name="dealdata",
            name="journal",
        ),
        migrations.AddField(
            model_name="journal",
            name="dealdata",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="PureOpenAlex.dealdata",
            ),
        ),
        migrations.AddField(
            model_name="journal",
            name="openalex_url",
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name="paper",
            name="topics",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="dealdata",
            name="jb_url",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="dealdata",
            name="publisher",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="journal",
            name="name",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="journal",
            name="publisher",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="location",
            name="landing_page_url",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="location",
            name="pdf_url",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="paper",
            name="pdf_link_primary",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="paper",
            name="primary_link",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="paper",
            name="title",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="pureentry",
            name="publisher",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="pureentry",
            name="rights",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="pureentry",
            name="title",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="source",
            name="display_name",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="source",
            name="homepage_url",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="source",
            name="host_org",
            field=models.CharField(max_length=512),
        ),
        migrations.AddField(
            model_name="affiliation",
            name="author",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="affiliations",
                to="PureOpenAlex.author",
            ),
        ),
        migrations.AddField(
            model_name="affiliation",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="affiliations",
                to="PureOpenAlex.organization",
            ),
        ),
        migrations.AddField(
            model_name="author",
            name="affils",
            field=models.ManyToManyField(
                blank=True,
                db_index=True,
                related_name="authors",
                through="PureOpenAlex.Affiliation",
                to="PureOpenAlex.organization",
            ),
        ),
        migrations.DeleteModel(
            name="AFASData",
        ),
        migrations.DeleteModel(
            name="JournalKeyword",
        ),
        migrations.AddField(
            model_name="journal",
            name="keywords",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.DeleteModel(
            name="Keyword",
        ),
        migrations.AddField(
            model_name="paper",
            name="keywords",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
