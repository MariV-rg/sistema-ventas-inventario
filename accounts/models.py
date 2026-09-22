from django.db import models
from django.contrib.auth.models import User


class Rol(models.Model):
    '''
    Cada fila es un rol posible del sistema (Administrador, Vendedor).
    Antes esto era solo un choices dentro de Perfil; ahora es su propia tabla
    para poder relacionar VARIOS roles con un mismo usuario (HU3).
    '''

    ADMINISTRADOR = 'ADMINISTRADOR'
    VENDEDOR = 'VENDEDOR'
    NOMBRE_CHOICES = [
        (ADMINISTRADOR, 'Administrador'),
        (VENDEDOR, 'Vendedor'),
    ]

    nombre = models.CharField(max_length=20, choices=NOMBRE_CHOICES, unique=True)

    def __str__(self):
        return self.get_nombre_display()


class Perfil(models.Model):
    '''
    Cada usuario tiene un Perfil, y ese Perfil puede tener VARIOS roles (HU3).
    '''

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    roles = models.ManyToManyField(Rol, related_name='perfiles', blank=True)

    def tiene_rol(self, nombre_rol):
        return self.roles.filter(nombre=nombre_rol).exists()

    def __str__(self):
        nombres = ', '.join(r.get_nombre_display() for r in self.roles.all())
        return f"{self.usuario.username} ({nombres or 'sin rol'})"