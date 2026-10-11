from django.shortcuts import render
from django.contrib.auth.models import User
from .models import Perfil, Rol
from .forms import RegistroUsuarioForm
from .decorators import rol_requerido


def es_administrador(user):
    '''
    Un superusuario (como el que creaste con createsuperuser) siempre puede.
    Cualquier otro usuario necesita tener, entre sus roles, el de Administrador.
    '''
    if user.is_superuser:
        return True
    return hasattr(user, 'perfil') and user.perfil.tiene_rol(Rol.ADMINISTRADOR)


@rol_requerido(Rol.ADMINISTRADOR)
def registrar_usuario(request):
    exito = False

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            nuevo_usuario = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1'],
            )
            perfil = Perfil.objects.create(usuario=nuevo_usuario)
            perfil.roles.set(form.cleaned_data['roles'])
            form = RegistroUsuarioForm()
            exito = True
    else:
        form = RegistroUsuarioForm()

    return render(request, 'registrar.html', {'form': form, 'exito': exito})