from django import template

register = template.Library()


@register.filter
def highest(value):
    """
    returns the max value of a list.
    """
    return max(value)
