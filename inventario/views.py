from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import rol_requerido
from accounts.models import Rol
from .models import Categoria, Producto


def a_decimal(texto, limite):
    '''
    Convierte el texto que escribió el usuario a Decimal.
    Devuelve None si no es un número válido, si es negativo o si es demasiado grande.
    '''
    try:
        numero = Decimal(texto)
    except (InvalidOperation, TypeError):
        return None
    if not numero.is_finite() or numero < 0 or numero >= limite:
        return None
    return numero


def validar_producto(post, excluir_id=None):
    '''
    Revisa los datos del formulario de producto (son los mismos al registrar y al editar).
    Devuelve (errors, limpios):
      - errors: lista de mensajes. Si está vacía, los datos son válidos.
      - limpios: los datos ya convertidos, listos para guardar.
    excluir_id: al editar, el id del propio producto (para que no choque con su mismo nombre).
    '''
    errors = []

    nombre = post.get('nombre', '').strip()
    categoria_id = post.get('categoria', '')
    precio = post.get('precio', '')
    unidad_base = post.get('unidad_base', '')
    stock_minimo = post.get('stock_minimo', '') or '0'   # 5F: si se deja vacío, queda en 0

    # 5B: campos obligatorios
    if not nombre:
        errors.append('El nombre es obligatorio.')
    elif len(nombre) > 100:
        errors.append('El nombre no puede tener más de 100 caracteres.')
    else:
        # 5C: no repetir productos (sin importar mayúsculas, tampoco en letras con tilde)
        otros = Producto.objects.exclude(id=excluir_id).values_list('nombre', flat=True)
        if nombre.casefold() in [otro.casefold() for otro in otros]:
            errors.append('Ya existe un producto con ese nombre.')

    categoria = None
    if categoria_id.isdigit():
        categoria = Categoria.objects.filter(id=categoria_id).first()
    if categoria is None:
        errors.append('Selecciona una categoría.')

    precio_dec = a_decimal(precio, 10 ** 8)
    if precio_dec is None:
        errors.append('El precio es obligatorio y debe ser un número mayor o igual a 0.')

    stock_dec = a_decimal(stock_minimo, 10 ** 7)
    if stock_dec is None:
        errors.append('El stock mínimo debe ser un número mayor o igual a 0.')

    # 5D / 5E: la unidad base solo se pide si la categoría se vende por peso
    if categoria is not None and categoria.es_peso_variable:
        if unidad_base not in dict(Producto.UNIDAD_BASE_CHOICES):
            errors.append('Esta categoría se vende por peso: elige la unidad base (kilo o gramo).')
    else:
        unidad_base = ''

    limpios = {
        'nombre': nombre,
        'categoria': categoria,
        'precio': precio_dec,
        'unidad_base': unidad_base,
        'stock_minimo': stock_dec,
    }
    return errors, limpios


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
    categorias = Categoria.objects.all()
    errors = []
    datos = {'stock_minimo': 0}   # valor inicial del formulario

    if request.method == 'POST':
        # Si algo sale mal, el formulario conserva lo que el usuario escribió
        datos = request.POST

        errors, limpios = validar_producto(request.POST)

        # 5A: si todo está bien, se registra el producto
        if not errors:
            producto = Producto.objects.create(
                nombre=limpios['nombre'],
                categoria=limpios['categoria'],
                precio=limpios['precio'],
                unidad_base=limpios['unidad_base'],
                stock_minimo=limpios['stock_minimo'],
            )
            messages.success(request, f'Producto "{producto.nombre}" registrado correctamente.')
            return redirect('registrar_producto')

    return render(request, 'registrar_producto.html', {
        'categorias': categorias,
        'errors': errors,
        'datos': datos,
    })

#HU6: editar producto

@rol_requerido(Rol.ADMINISTRADOR)
def editar_producto(request, id):
    # Solo se pueden editar productos activos (los "eliminados" de HU7 no aparecen)
    producto = get_object_or_404(Producto, id=id, activo=True)
    categorias = Categoria.objects.all()
    errors = []

    # Datos que se muestran en el formulario: los actuales del producto
    datos = {
        'nombre': producto.nombre,
        'categoria': str(producto.categoria_id),
        'precio': format(producto.precio, 'f'),
        'unidad_base': producto.unidad_base,
        'stock_minimo': format(producto.stock_minimo.normalize(), 'f'),
    }

    if request.method == 'POST':
        # Si algo sale mal, el formulario conserva lo que el usuario escribió
        datos = request.POST

        # 6B: las mismas validaciones del registro (HU5).
        # excluir_id evita que choque con su propio nombre.
        errors, limpios = validar_producto(request.POST, excluir_id=producto.id)

        # 6A: si todo está bien, se actualiza el producto
        if not errors:
            producto.nombre = limpios['nombre']
            producto.categoria = limpios['categoria']
            producto.precio = limpios['precio']
            producto.unidad_base = limpios['unidad_base']
            producto.stock_minimo = limpios['stock_minimo']
            producto.save()

            messages.success(request, f'Producto "{producto.nombre}" actualizado correctamente.')
            return redirect('lista_productos')

    return render(request, 'editar_producto.html', {
        'producto': producto,
        'categorias': categorias,
        'errors': errors,
        'datos': datos,
    })


# HU7: eliminar producto

@rol_requerido(Rol.ADMINISTRADOR)
@require_POST
def eliminar_producto(request, id):
    # 7B: "eliminar" = marcar como inactivo (no se borra de la base de datos)
    producto = get_object_or_404(Producto, id=id, activo=True)
    producto.activo = False
    producto.save(update_fields=['activo'])

    messages.success(request, f'Producto "{producto.nombre}" eliminado correctamente.')
    return redirect('lista_productos')