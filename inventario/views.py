from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import formats
from django.views.decorators.http import require_POST

from accounts.decorators import rol_requerido
from accounts.models import Rol
from .models import Caja, Categoria, Producto
from .forms import CajaForm


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
    # HU8: los productos activos se muestran agrupados por categoría
    # (HU7: "eliminar" los pone en activo=False y por eso no salen)
    grupos = []
    for categoria in Categoria.objects.all():
        productos = list(Producto.objects.filter(activo=True, categoria=categoria))
        if productos:
            grupos.append({'categoria': categoria, 'productos': productos})
    return render(request, 'productos_lista.html', {'grupos': grupos})

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


def caja_abierta_del_vendedor(usuario):
    '''
    Devuelve la caja abierta del vendedor, o None si no tiene ninguna.
    '''
    return Caja.objects.filter(
        vendedor=usuario,
        estado=Caja.ESTADO_ABIERTA,
    ).first()


def caja_abierta_requerida(vista):
    '''
    HU12 (12D): bloquea una vista si el vendedor no tiene la caja abierta.
    Se usa en la vista de registrar venta.
    '''
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if caja_abierta_del_vendedor(request.user) is None:
            messages.error(
                request,
                'No puede registrar ventas: primero debe abrir la caja.',
            )
            return redirect('abrir_caja')
        return vista(request, *args, **kwargs)
    return envoltura


@rol_requerido(Rol.VENDEDOR)
def abrir_caja(request):
    '''
    HU12: el vendedor abre la caja registrando el monto inicial del turno.
    '''
    # 12B: ya hay una caja abierta
    if caja_abierta_del_vendedor(request.user):
        messages.warning(request, 'Ya hay una caja abierta.')
        return redirect('home')

    if request.method == 'POST':
        form = CajaForm(request.POST)
        # 12C: si el monto viene vacío, el formulario no es válido
        if form.is_valid():
            # 12A: se guarda el monto como base de apertura del día
            caja = form.save(commit=False)
            caja.vendedor = request.user
            caja.save()
            messages.success(request, 'Caja abierta correctamente.')
            return redirect('home')
    else:
        form = CajaForm()

    return render(request, 'abrir_caja.html', {'form': form})
# HU9: consultar inventario

@rol_requerido(Rol.ADMINISTRADOR)
def consultar_inventario(request):
    # 9A: todos los productos activos con su cantidad disponible
    productos = Producto.objects.filter(activo=True).select_related('categoria')
    # HU10: cuántos están por debajo de su mínimo (para el aviso de arriba)
    cantidad_alertas = productos.filter(stock__lt=F('stock_minimo')).count()
    stock_normal = productos.count() - cantidad_alertas
    return render(request, 'inventario_lista.html', {
        'productos': productos,
        'cantidad_alertas': cantidad_alertas,
        'stock_normal': stock_normal,
    })


# HU10: alertas de stock bajo

@rol_requerido(Rol.ADMINISTRADOR)
def alertas_stock(request):
    # 10A: productos cuyo stock está por debajo del mínimo definido.
    # 10C: la lista se calcula cada vez que se abre, así que al reabastecer (HU11)
    # el producto desaparece solo.
    productos = Producto.objects.filter(
        activo=True, stock__lt=F('stock_minimo')
    ).select_related('categoria')
    return render(request, 'alertas_stock.html', {'productos': productos})


# HU11: registrar ingreso de nuevas unidades

@rol_requerido(Rol.ADMINISTRADOR)
def ingresar_unidades(request, id):
    producto = get_object_or_404(Producto, id=id, activo=True)
    es_peso = producto.categoria.es_peso_variable
    errors = []
    datos = {}

    if request.method == 'POST':
        # Si algo sale mal, el formulario conserva lo que el usuario escribió
        datos = request.POST

        cantidad = a_decimal(request.POST.get('cantidad', '').strip(), 10 ** 7)

        # 11B: la cantidad tiene que ser un número mayor que 0
        if cantidad is None or cantidad <= 0:
            errors.append('La cantidad debe ser un número mayor que 0.')
        elif cantidad.as_tuple().exponent < -3:
            errors.append('La cantidad puede tener máximo 3 decimales.')
        # 5E: los productos por unidad no se cuentan en fracciones
        elif not es_peso and cantidad != cantidad.to_integral_value():
            errors.append('Este producto se maneja por unidades: ingresa un número entero.')
        elif producto.stock + cantidad >= 10 ** 7:
            errors.append('Con esa cantidad el stock superaría el máximo permitido.')

        # 11A: si todo está bien, la cantidad se suma al stock actual.
        # 10C: como las alertas se calculan al abrirlas, el producto sale solo si ya supera el mínimo.
        if not errors:
            producto.stock += cantidad
            producto.save(update_fields=['stock'])

            messages.success(
                request,
                f'Ingreso registrado: {formats.localize(cantidad.normalize())} para "{producto.nombre}". '
                f'Stock actual: {formats.localize(producto.stock.normalize())}.'
            )
            return redirect('consultar_inventario')

    return render(request, 'ingresar_unidades.html', {
        'producto': producto,
        'errors': errors,
        'datos': datos,
    })
