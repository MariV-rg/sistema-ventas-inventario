from django.db import models
from django.contrib.auth.models import User


class Perfil(models.Model):
    '''
    Guarda el rol de cada usuario del sistema (HU2).
    Está enlazado 1 a 1 con el User de Django: cada usuario tiene un solo Perfil.
    '''

    ADMINISTRADOR = 'ADMINISTRADOR'
    VENDEDOR = 'VENDEDOR'
    ROL_CHOICES = [
        (ADMINISTRADOR, 'Administrador'),
        (VENDEDOR, 'Vendedor'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=20, choices=ROL_CHOICES)

    def __str__(self):
        return f"{self.usuario.username} ({self.get_rol_display()})"