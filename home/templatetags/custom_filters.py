from django import template

register = template.Library()

@register.filter(name='to_int')
def to_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

@register.filter(name='get_range')
def get_range(start, end): 
    try:
        return range(start, end + 1)
    except:
        return []