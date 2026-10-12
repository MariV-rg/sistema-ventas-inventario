from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.decorators import rol_requerido
from accounts.models import Rol
from .forms import ProductoForm
from .models import Categoria, Producto


@login_required
def home(request):
    return render(request, 'home.html')


@rol_requerido(Rol.ADMINISTRADOR)
def lista_productos(request):
    # Solo productos activos (HU7: "eliminar" los pone en activo=False)
    productos = Producto.objects.filter(activo=True).select_related('categoria')
    return render(request, 'productos_lista.html', {'productos': productos})


@rol_requerido(Rol.ADMINISTRADOR)
def registrar_producto(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f'Producto "{producto.nombre}" registrado correctamente.')
            return redirect('registrar_producto')
    else:
        form = ProductoForm()

    # Ids de las categorías por peso: la plantilla los usa para mostrar/ocultar "unidad base"
    categorias_peso = list(
        Categoria.objects.filter(es_peso_variable=True).values_list('id', flat=True)
    )
    return render(request, 'registrar_producto.html', {
        'form': form,
        'categorias_peso': categorias_peso,
    })