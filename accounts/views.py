from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from .models import Perfil, Rol
from .forms import ConfiguracionInicialForm, RegistroUsuarioForm
from .decorators import rol_requerido


def es_administrador(user):
    '''
    Un superusuario (como el que creaste con createsuperuser) siempre puede.
    Cualquier otro usuario necesita tener, entre sus roles, el de Administrador.
    '''
    if user.is_superuser:
        return True
    return hasattr(user, 'perfil') and user.perfil.tiene_rol(Rol.ADMINISTRADOR)


def es_administrador_principal(user):
    '''
    HU29: el administrador principal es el superusuario (el que se crea con createsuperuser).
    Solo él puede crear otros administradores y dar o quitar el rol Administrador.
    La futura pantalla de administrar usuarios (HU28) debe usar esta misma función.
    '''
    return user.is_superuser


@rol_requerido(Rol.ADMINISTRADOR)
def registrar_usuario(request):
    exito = False

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST, quien_registra=request.user)
        if form.is_valid():
            nuevo_usuario = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1'],
            )
            perfil = Perfil.objects.create(usuario=nuevo_usuario)
            perfil.roles.set(form.cleaned_data['roles'])
            form = RegistroUsuarioForm(quien_registra=request.user)
            exito = True
    else:
        form = RegistroUsuarioForm(quien_registra=request.user)

    return render(request, 'registrar.html', {
        'form': form,
        'exito': exito,
        'es_principal': es_administrador_principal(request.user),
    })


class LoginConConfiguracionInicial(LoginView):
    '''
    El inicio de sesión de siempre, con una diferencia (29F): si el sistema todavía no tiene
    ningún usuario, en vez del login se muestra la configuración inicial. Como todas las
    pantallas mandan al login a quien no ha entrado, basta con abrir la aplicación.
    '''
    template_name = 'login.html'

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect('configuracion_inicial')
        return super().dispatch(request, *args, **kwargs)


def configuracion_inicial(request):
    # 29G: solo funciona mientras no exista ningún usuario. Después, nadie puede usarla
    # para crearse una cuenta de administrador.
    if User.objects.exists():
        messages.error(request, 'El sistema ya está configurado. Inicia sesión.')
        return redirect('login')

    if request.method == 'POST':
        form = ConfiguracionInicialForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                if User.objects.exists():          # por si otra persona lo creó justo antes
                    return redirect('login')
                usuario = User.objects.create_superuser(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password1'],
                )
                perfil = Perfil.objects.create(usuario=usuario)
                perfil.roles.set(Rol.objects.filter(nombre=Rol.ADMINISTRADOR))
            login(request, usuario)                # queda con la sesión iniciada
            return redirect('home')
    else:
        form = ConfiguracionInicialForm()

    return render(request, 'configuracion_inicial.html', {'form': form})