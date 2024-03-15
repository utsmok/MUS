from django import template

register = template.Library()


@register.filter
def concat(value,arg):
    """
    concats string arg to value
    """

    return str(value)+str(arg)
