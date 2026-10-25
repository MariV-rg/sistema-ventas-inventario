from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import redirect, render
from django.utils import formats
from django.views.decorators.http import require_POST

from accounts.decorators import rol_requerido
from accounts.models import Rol
from inventario.models import Categoria, Producto
from .models import Caja, DetalleVenta, Venta


# ---------------------------------------------------------------
# Funciones de apoyo
# ---------------------------------------------------------------

def unidad_corta(producto):
    '''Unidad en la que se maneja el producto: kg, g o und.'''
    if producto.categoria.es_peso_variable:
        return 'kg' if producto.unidad_base == Producto.UNIDAD_KILO else 'g'
    return 'und'


def caja_abierta(usuario):
    '''La caja que tiene abierta este usuario, o None si no tiene ninguna.'''
    return Caja.objects.filter(vendedor=usuario, abierta=True).select_related('vendedor').first()


def caja_requerida(vista):
    '''
    12D: si el vendedor no tiene su caja abierta, no puede vender. Lo manda a abrirla.
    Se pone debajo de @rol_requerido en las vistas de venta.
    '''
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if caja_abierta(request.user) is None:
            messages.error(request, 'Primero debes abrir tu caja para registrar ventas.')
            return redirect('abrir_caja')
        return vista(request, *args, **kwargs)
    return envoltura


def leer_carrito(request):
    '''
    La venta que se está armando vive en la sesión del vendedor (todavía no está en la base
    de datos): {id_del_producto: cantidad}. La cantidad se guarda como texto.
    '''
    return request.session.get('carrito', {})


def guardar_carrito(request, carrito):
    request.session['carrito'] = carrito


def calcular_subtotal(precio, cantidad):
    # 14G: el precio es por unidad base (kilo, gramo o unidad), así que se calcula proporcional
    return (precio * cantidad).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def armar_resumen(carrito):
    '''
    Convierte el carrito en líneas (producto, cantidad, subtotal) y calcula el total.
    14B / 14C: el total se calcula cada vez, así que siempre está al día.
    '''
    productos = Producto.objects.filter(id__in=carrito.keys(), activo=True).select_related('categoria')
    lineas = []
    total = Decimal('0')
    for producto in productos:
        cantidad = Decimal(carrito[str(producto.id)])
        subtotal = calcular_subtotal(producto.precio, cantidad)
        lineas.append({
            'producto': producto,
            'cantidad': cantidad,
            'unidad': unidad_corta(producto),
            'subtotal': subtotal,
        })
        total += subtotal
    return lineas, total


def convertir_a_unidad_base(producto, cantidad, unidad):
    '''
    14F: el vendedor puede escribir el peso en gramos o en kilos.
    Aquí se convierte a la unidad en la que está guardado el producto.
    '''
    if not producto.categoria.es_peso_variable:
        return cantidad
    if producto.unidad_base == Producto.UNIDAD_KILO and unidad == 'g':
        return cantidad / 1000
    if producto.unidad_base == Producto.UNIDAD_GRAMO and unidad == 'kg':
        return cantidad * 1000
    return cantidad


def validar_cantidad(producto, texto, unidad, ya_en_la_venta=Decimal('0')):
    '''
    Revisa la cantidad que escribió el vendedor.
    Devuelve (errors, cantidad en la unidad base del producto).
    ya_en_la_venta: lo que ese producto ya tiene en la venta (para no pasarse del stock).
    '''
    errors = []
    try:
        cantidad = Decimal(texto.strip())
    except InvalidOperation:
        return ['La cantidad debe ser un número.'], None

    if not cantidad.is_finite() or cantidad <= 0:
        return ['La cantidad debe ser un número mayor que 0.'], None

    es_peso = producto.categoria.es_peso_variable
    if es_peso and unidad not in ('g', 'kg'):
        return ['Elige la unidad del peso: gramos o kilos.'], None

    cantidad = convertir_a_unidad_base(producto, cantidad, unidad)

    if cantidad.as_tuple().exponent < -3:
        errors.append('La cantidad es demasiado precisa (máximo 3 decimales en la unidad del producto).')
    elif not es_peso and cantidad != cantidad.to_integral_value():
        errors.append('Este producto se vende por unidades: ingresa un número entero.')
    elif cantidad + ya_en_la_venta > producto.stock:
        # 14E: no se puede vender más de lo que hay
        errors.append(
            f'No hay suficientes unidades de "{producto.nombre}". '
            f'Disponible: {formats.localize(producto.stock.normalize())} {unidad_corta(producto)}.'
        )
    return errors, (None if errors else cantidad)


# ---------------------------------------------------------------
# HU12: apertura de caja
# ---------------------------------------------------------------

@rol_requerido(Rol.VENDEDOR)
def abrir_caja(request):
    caja = caja_abierta(request.user)                  # la caja de este vendedor
    # las cajas abiertas de los demás vendedores (para saber quién la tiene abierta)
    otras_cajas = Caja.objects.filter(abierta=True).exclude(vendedor=request.user).select_related('vendedor')
    errors = []
    datos = {}

    if request.method == 'POST':
        datos = request.POST

        # 12B: si ya tiene su caja abierta, no se puede abrir otra
        if caja is not None:
            messages.error(request, 'Ya tienes una caja abierta.')
            return redirect('abrir_caja')

        # 12C: el monto inicial es obligatorio
        texto = request.POST.get('monto_inicial', '').strip()
        if not texto:
            errors.append('El monto inicial es obligatorio.')
        else:
            try:
                monto = Decimal(texto)
            except InvalidOperation:
                monto = None
            if monto is None or not monto.is_finite():
                errors.append('El monto inicial debe ser un número.')
            elif monto < 0:
                errors.append('El monto inicial no puede ser negativo.')
            elif monto.as_tuple().exponent < -2:
                errors.append('El monto inicial puede tener máximo 2 decimales.')
            elif monto >= 10 ** 10:
                errors.append('El monto inicial es demasiado grande.')

        # 12A: si todo está bien, el monto queda como base de apertura de su caja
        if not errors:
            try:
                with transaction.atomic():
                    Caja.objects.create(vendedor=request.user, monto_inicial=monto)
            except IntegrityError:
                # por ejemplo, si pulsó el botón dos veces: la primera ya la abrió
                messages.error(request, 'Ya tienes una caja abierta.')
                return redirect('abrir_caja')
            messages.success(request, 'Caja abierta. Ya puedes registrar ventas.')
            return redirect('nueva_venta')

    return render(request, 'abrir_caja.html', {
        'caja': caja,
        'otras_cajas': otras_cajas,
        'errors': errors,
        'datos': datos,
    })


# ---------------------------------------------------------------
# HU14: registrar venta
# ---------------------------------------------------------------

@rol_requerido(Rol.VENDEDOR)
@caja_requerida
def nueva_venta(request):
    lineas, total = armar_resumen(leer_carrito(request))

    # HU13: productos que el vendedor puede ver al vender, agrupados por categoría.
    # Salen todos los productos activos: los que no tienen existencias se muestran
    # como "No disponible" (13B).
    grupos = []
    for categoria in Categoria.objects.all():
        productos = list(Producto.objects.filter(activo=True, categoria=categoria))
        if productos:
            for producto in productos:
                producto.categoria = categoria
                producto.unidad = unidad_corta(producto)
            grupos.append({'categoria': categoria, 'productos': productos})

    return render(request, 'nueva_venta.html', {
        'grupos': grupos,
        'lineas': lineas,
        'total': total,
        'metodos_pago': Venta.METODO_PAGO_CHOICES,
        'caja': caja_abierta(request.user),
    })


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
@require_POST
def agregar_al_carrito(request):
    # 14A: el vendedor elige un producto y una cantidad
    producto_id = request.POST.get('producto', '')
    producto = None
    if producto_id.isdigit():
        producto = Producto.objects.filter(
            id=producto_id, activo=True, stock__gt=0
        ).select_related('categoria').first()
    if producto is None:
        messages.error(request, 'Selecciona un producto disponible.')
        return redirect('nueva_venta')

    carrito = leer_carrito(request)
    ya_en_la_venta = Decimal(carrito.get(str(producto.id), '0'))

    cantidad_texto = request.POST.get('cantidad', '')
    unidad = request.POST.get('unidad', '')

    # 14H: accesos rápidos de peso (250 g, 500 g, 1 kg). Solo aplican a productos por peso
    # y no impiden escribir cualquier otro peso a mano.
    atajos = {'250g': ('250', 'g'), '500g': ('500', 'g'), '1kg': ('1', 'kg')}
    atajo = request.POST.get('atajo', '')
    if producto.categoria.es_peso_variable and atajo in atajos:
        cantidad_texto, unidad = atajos[atajo]

    errors, cantidad = validar_cantidad(producto, cantidad_texto, unidad, ya_en_la_venta)
    if errors:
        for error in errors:
            messages.error(request, error)
    else:
        # si el producto ya estaba en la venta, se suma a lo que había
        carrito[str(producto.id)] = str(ya_en_la_venta + cantidad)
        guardar_carrito(request, carrito)
    return redirect('nueva_venta')


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
@require_POST
def actualizar_carrito(request, producto_id):
    # 14C: al cambiar una cantidad, el total se recalcula (se calcula al mostrar la página)
    carrito = leer_carrito(request)
    producto = Producto.objects.filter(id=producto_id, activo=True).select_related('categoria').first()
    if producto is None or str(producto_id) not in carrito:
        messages.error(request, 'Ese producto no está en la venta.')
        return redirect('nueva_venta')

    errors, cantidad = validar_cantidad(
        producto, request.POST.get('cantidad', ''), request.POST.get('unidad', '')
    )
    if errors:
        for error in errors:
            messages.error(request, error)
    else:
        carrito[str(producto_id)] = str(cantidad)    # reemplaza la cantidad anterior
        guardar_carrito(request, carrito)
    return redirect('nueva_venta')


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
@require_POST
def quitar_del_carrito(request, producto_id):
    carrito = leer_carrito(request)
    carrito.pop(str(producto_id), None)
    guardar_carrito(request, carrito)
    return redirect('nueva_venta')


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
@require_POST
def confirmar_venta(request):
    carrito = leer_carrito(request)
    metodo_pago = request.POST.get('metodo_pago', '')
    errors = []

    if not carrito:
        errors.append('Agrega al menos un producto a la venta.')
    # 14I: hay que elegir el método de pago
    if metodo_pago not in dict(Venta.METODO_PAGO_CHOICES):
        errors.append('Selecciona el método de pago.')
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('nueva_venta')

    with transaction.atomic():
        # se bloquean los productos mientras se guarda la venta, para que dos ventas
        # al mismo tiempo no se coman el mismo stock
        productos = {
            p.id: p for p in Producto.objects.select_for_update().filter(id__in=carrito.keys(), activo=True)
        }

        # 14E: se revisa el stock otra vez, porque pudo cambiar desde que se armó la venta
        for producto_id, texto in carrito.items():
            producto = productos.get(int(producto_id))
            if producto is None:
                errors.append('Un producto de la venta ya no está disponible. Quítalo e intenta de nuevo.')
            elif Decimal(texto) > producto.stock:
                errors.append(f'No hay suficientes unidades de "{producto.nombre}".')
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('nueva_venta')

        # 12D: su caja tiene que seguir abierta al guardar (pudo cerrarse mientras armaba la venta)
        caja = Caja.objects.select_for_update().filter(vendedor=request.user, abierta=True).first()
        if caja is None:
            messages.error(request, 'Primero debes abrir tu caja para registrar ventas.')
            return redirect('abrir_caja')

        venta = Venta.objects.create(vendedor=request.user, metodo_pago=metodo_pago, caja=caja)
        total = Decimal('0')
        for producto_id, texto in carrito.items():
            producto = productos[int(producto_id)]
            cantidad = Decimal(texto)
            subtotal = calcular_subtotal(producto.precio, cantidad)
            DetalleVenta.objects.create(
                venta=venta, producto=producto, cantidad=cantidad,
                precio_unitario=producto.precio, subtotal=subtotal,
            )
            # 14D: se descuenta del inventario lo que se vendió
            Producto.objects.filter(id=producto.id).update(stock=F('stock') - cantidad)
            total += subtotal
        venta.total = total
        venta.save(update_fields=['total'])

    request.session.pop('carrito', None)
    messages.success(
        request,
        f'Venta #{venta.id} registrada. Total: ${formats.number_format(total, decimal_pos=0, force_grouping=True)} '
        f'({venta.get_metodo_pago_display()}).'
    )
    return redirect('nueva_venta')