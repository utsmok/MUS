from django import template

register = template.Library()


@register.filter
def lowest(value):
    """
    returns the min value of a list.
    """ 
    return min(value)
