'''
TODO: add functions for manual data repair (suggestions?)

e.g. add a form / checkmark in single_article.html in certain fields to let the user update
fields like paper.is_in_pure or paper.has_pure_oai_match

make a new model class as well to keep track of these manual changes
e.g.:

class ManualEdit(models.Model):
    target_paper=models.ForeignKey(Paper, on_delete=models.CASCADE)
    target_pureentry=models.ForeignKey(PureEntry, on_delete=models.CASCADE)
    target_author=models.ForeignKey(Author, on_delete=models.CASCADE)
    target_utdata=models.ForeignKey(UTData, on_delete=models.CASCADE)
    target_journal=models.ForeignKey(Journal, on_delete=models.CASCADE)
    target_source=models.ForeignKey(Source, on_delete=models.CASCADE)
    target_authorship=models.ForeignKey(Authorship, on_delete=models.CASCADE)

    edited_field=models.CharField(max_length=255)
    old_value=models.CharField(max_length=255)
    new_value=models.CharField(max_length=255)
'''