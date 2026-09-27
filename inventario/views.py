from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import rol_requerido
from accounts.models import Rol
from .forms import ProductoForm


@login_required
def home(request):
    return render(request, 'home.html')

@rol_requerido(Rol.ADMINISTRADOR)
def registrar_producto(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto registrado correctamente.')
            return redirect('registrar_producto')
        else:
            messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = ProductoForm()

    return render(request, 'registrar_producto.html', {'form': form})