from django.db import migrations

# (nombre, ¿se vende por peso?)
CATEGORIAS_INICIALES = [
    ('Aseo', False),
    ('Plaza', True),
    ('Licor', False),
    ('Snacks', False),
    ('Mercado', False),
]


def crear_categorias(apps, schema_editor):
    Categoria = apps.get_model('inventario', 'Categoria')
    for nombre, es_peso in CATEGORIAS_INICIALES:
        Categoria.objects.get_or_create(nombre=nombre, defaults={'es_peso_variable': es_peso})


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_categorias, migrations.RunPython.noop),
    ]