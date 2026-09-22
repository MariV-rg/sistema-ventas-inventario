from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def rol_requerido(*roles_permitidos):
    '''
    Decorador para vistas que solo puede usar gente con alguno de los roles indicados.
    Un superusuario siempre pasa.

    Uso:
        @rol_requerido(Rol.ADMINISTRADOR)
        def eliminar_producto(request):
            ...

    Si el usuario no cumple, lo manda de vuelta con un mensaje de error (HU4 - 4A).
    '''
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if request.user.is_superuser:
                return vista(request, *args, **kwargs)

            perfil = getattr(request.user, 'perfil', None)
            if perfil and perfil.roles.filter(nombre__in=roles_permitidos).exists():
                return vista(request, *args, **kwargs)

            messages.error(request, 'No tienes permisos suficientes para realizar esa acción.')
            return redirect('home')
        return envoltura
    return decorador