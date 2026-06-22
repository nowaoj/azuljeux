from django import template
from django.conf import settings

register = template.Library()

COLOR_HEX = {
    'BLUE': '#0066CC', 'YELLOW': '#FFCC00', 'RED': '#CC3333',
    'BLACK': '#444444', 'WHITE': '#DDDDDD',
}


@register.simple_tag
def tile_html(color_val, size='sm'):
    slug = {0: 'blue', 1: 'yellow', 2: 'red', 3: 'black', 4: 'white'}.get(color_val, '')
    assets = settings.STATIC_URL.rstrip('/') + '/assets/'
    if slug:
        return '<span class="tile %s" style="background:%s"></span>' % (
            size, COLOR_HEX.get(slug.upper(), '#888'))
    return '<span class="tile %s" style="background:#888"></span>' % size


@register.simple_tag
def color_hex(name):
    return COLOR_HEX.get(name.upper(), '#888')


@register.filter
def times(n):
    return list(range(n))


@register.filter
def index(lst, i):
    try:
        return lst[int(i)]
    except (IndexError, ValueError, TypeError):
        return None
