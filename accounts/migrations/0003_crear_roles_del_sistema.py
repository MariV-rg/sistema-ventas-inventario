from django.db import migrations


def crear_roles(apps, schema_editor):
    """
    Crea los roles del sistema. Si ya existen (como en una base de datos que ya se venía usando),
    no hace nada. Así nadie tiene que crearlos a mano en el panel de administración de Django.
    """
    Rol = apps.get_model('accounts', 'Rol')
    for nombre in ('ADMINISTRADOR', 'VENDEDOR'):
        Rol.objects.get_or_create(nombre=nombre)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_rol_remove_perfil_rol_perfil_roles'),
    ]

    operations = [
        migrations.RunPython(crear_roles, migrations.RunPython.noop),
    ]