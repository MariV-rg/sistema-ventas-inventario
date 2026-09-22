from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Perfil
from .forms import RegistroUsuarioForm


def es_administrador(user):
    '''
    Un superusuario (como el que creaste con createsuperuser) siempre puede.
    Cualquier otro usuario necesita tener Perfil con rol Administrador.
    '''
    if user.is_superuser:
        return True
    return hasattr(user, 'perfil') and user.perfil.rol == Perfil.ADMINISTRADOR


@login_required
def registrar_usuario(request):
    if not es_administrador(request.user):
        return redirect('home')

    exito = False

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            nuevo_usuario = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1'],
            )
            Perfil.objects.create(usuario=nuevo_usuario, rol=form.cleaned_data['rol'])
            form = RegistroUsuarioForm()  # formulario limpio para registrar otro
            exito = True
    else:
        form = RegistroUsuarioForm()

    return render(request, 'registrar.html', {'form': form, 'exito': exito})