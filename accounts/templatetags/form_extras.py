from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(bound_field, css_classes: str):
    try:
        widget = bound_field.field.widget
        existing = widget.attrs.get("class", "").strip()
        merged = f"{existing} {css_classes}".strip() if existing else css_classes
        attrs = {**widget.attrs, "class": merged}
        return bound_field.as_widget(attrs=attrs)
    except Exception:
        return getattr(bound_field, "as_widget", lambda **_: bound_field)()


@register.filter(name="add_attr")
def add_attr(bound_field, arg: str):
    try:
        key, value = arg.split(":", 1)
        widget = bound_field.field.widget
        attrs = {**widget.attrs, key: value}
        return bound_field.as_widget(attrs=attrs)
    except Exception:
        return getattr(bound_field, "as_widget", lambda **_: bound_field)()


@register.filter(name='split')
def split(value, key):
    return value.split(key)