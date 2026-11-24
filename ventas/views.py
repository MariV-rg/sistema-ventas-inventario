from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import formats, timezone
from django.views.decorators.http import require_POST

from accounts.decorators import rol_requerido
from accounts.models import Rol
from inventario.models import Categoria, Producto
from .models import Caja, DetalleVenta, Devolucion, RegistroBaja, Venta


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


def leer_monto(texto, nombre):
    '''
    Revisa un monto de dinero escrito por el vendedor (monto inicial o monto contado).
    Devuelve (monto, error). Si hay error, el monto es None.
    '''
    texto = texto.strip()
    if not texto:
        return None, f'{nombre} es obligatorio.'
    try:
        monto = Decimal(texto)
    except InvalidOperation:
        return None, f'{nombre} debe ser un número.'
    if not monto.is_finite():
        return None, f'{nombre} debe ser un número.'
    if monto < 0:
        return None, f'{nombre} no puede ser negativo.'
    if monto.as_tuple().exponent < -2:
        return None, f'{nombre} puede tener máximo 2 decimales.'
    if monto >= 10 ** 10:
        return None, f'{nombre} es demasiado grande.'
    return monto, None


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
        monto, error = leer_monto(request.POST.get('monto_inicial', ''), 'El monto inicial')
        if error:
            errors.append(error)

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


# ---------------------------------------------------------------
# HU16: cancelar venta en proceso
# ---------------------------------------------------------------

@rol_requerido(Rol.VENDEDOR)
@caja_requerida
@require_POST
def cancelar_venta(request):
    # 16A: la venta en proceso solo existe en la sesión del vendedor (todavía no se guardó ni
    # se descontó nada del inventario), así que cancelar es simplemente descartarla.
    if leer_carrito(request):
        request.session.pop('carrito', None)
        messages.success(request, 'Venta cancelada. No se descontó nada del inventario.')
    else:
        messages.error(request, 'No hay ninguna venta en proceso para cancelar.')
    return redirect('nueva_venta')


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
def revisar_venta(request):
    # HU15: la factura para revisar antes de confirmar. Aquí se elige el método de pago.
    carrito = leer_carrito(request)
    lineas, total = armar_resumen(carrito)
    if not lineas:
        messages.error(request, 'Agrega al menos un producto a la venta.')
        return redirect('nueva_venta')

    # 15A: se avisa de lo que haya que corregir (por ejemplo, si el stock cambió)
    problemas = []
    if len(lineas) != len(carrito):
        problemas.append('Un producto de la venta ya no está disponible. Quítalo en "Corregir venta".')
    for linea in lineas:
        producto = linea['producto']
        if linea['cantidad'] > producto.stock:
            problemas.append(
                f'No hay suficientes unidades de "{producto.nombre}". '
                f'Disponible: {formats.localize(producto.stock.normalize())} {linea["unidad"]}.'
            )

    return render(request, 'revisar_venta.html', {
        'lineas': lineas,
        'total': total,
        'problemas': problemas,
        'metodos_pago': Venta.METODO_PAGO_CHOICES,
        'caja': caja_abierta(request.user),
        'ahora': timezone.now(),
    })


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
@require_POST
def confirmar_venta(request):
    carrito = leer_carrito(request)
    metodo_pago = request.POST.get('metodo_pago', '')
    errors = []

    if not carrito:
        messages.error(request, 'Agrega al menos un producto a la venta.')
        return redirect('nueva_venta')
    # 14I: hay que elegir el método de pago
    if metodo_pago not in dict(Venta.METODO_PAGO_CHOICES):
        messages.error(request, 'Selecciona el método de pago.')
        return redirect('revisar_venta')

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
            return redirect('revisar_venta')

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


# ---------------------------------------------------------------
# HU18: cierre de caja
# ---------------------------------------------------------------

@rol_requerido(Rol.VENDEDOR)
def cerrar_caja(request):
    caja = caja_abierta(request.user)
    if caja is None:
        messages.error(request, 'No tienes una caja abierta para cerrar.')
        return redirect('abrir_caja')

    errors = []
    datos = {}

    if request.method == 'POST':
        datos = request.POST

        # 18A: el vendedor registra el monto final contado
        monto, error = leer_monto(request.POST.get('monto_final', ''), 'El monto contado')
        if error:
            errors.append(error)
        else:
            with transaction.atomic():
                caja = Caja.objects.select_for_update().filter(vendedor=request.user, abierta=True).first()
                if caja is None:
                    messages.error(request, 'Tu caja ya estaba cerrada.')
                    return redirect('abrir_caja')
                # 18A y 18B: compara contra lo esperado y guarda el descuadre
                caja.cerrar(monto)

            # 18C: al cerrar, ya no se puede vender hasta abrir una nueva caja
            request.session.pop('carrito', None)      # la venta que estaba a medias se descarta
            messages.success(request, 'Caja cerrada.')
            return redirect('resultado_cierre', caja_id=caja.id)

    return render(request, 'cerrar_caja.html', {
        'caja': caja,
        'errors': errors,
        'datos': datos,
    })


@rol_requerido(Rol.VENDEDOR)
def resultado_cierre(request, caja_id):
    # 18B: muestra lo esperado, lo contado y el descuadre (solo el dueño de la caja)
    caja = get_object_or_404(Caja, id=caja_id, vendedor=request.user, abierta=False)
    return render(request, 'resultado_cierre.html', {'caja': caja})


# ---------------------------------------------------------------
# HU17: devoluciones
# ---------------------------------------------------------------

def destino_de_la_unidad(motivo, producto, reutilizable):
    """
    Decide a dónde va la unidad que el cliente devolvió:
      - producto diferente al comprado: está en buen estado, vuelve al inventario;
      - motivo "otro": el vendedor dice si se puede volver a vender;
      - vencido, defectuoso o vicio oculto: no se puede vender; si el proveedor recibe
        cambios queda "para cambio", y si no, se registra como pérdida.
    """
    if motivo == Devolucion.MOTIVO_DIFERENTE:
        return Devolucion.DESTINO_STOCK
    if motivo == Devolucion.MOTIVO_OTRO and reutilizable == 'si':
        return Devolucion.DESTINO_STOCK
    if producto.recibe_cambio:
        return Devolucion.DESTINO_CAMBIO
    return Devolucion.DESTINO_PERDIDA


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
def devoluciones(request):
    # lista de ventas confirmadas, para elegir de cuál se devuelve un producto
    ventas = Venta.objects.select_related('vendedor').prefetch_related('detalles__producto')
    busqueda = request.GET.get('q', '').strip().lstrip('#')
    if busqueda:
        ventas = ventas.filter(id=busqueda) if busqueda.isdigit() else ventas.none()
    return render(request, 'devoluciones_lista.html', {
        'ventas': ventas[:50],
        'busqueda': request.GET.get('q', ''),
        'caja': caja_abierta(request.user),
    })


def lineas_de_devolucion(venta):
    """Las líneas de la venta con lo vendido, lo ya devuelto y lo que todavía se puede devolver."""
    lineas = []
    for detalle in venta.detalles.select_related('producto__categoria'):
        lineas.append({
            'detalle': detalle,
            'unidad': unidad_corta(detalle.producto),
            'es_peso': detalle.producto.categoria.es_peso_variable,
            'devuelta': detalle.cantidad_devuelta(),
            'disponible': detalle.cantidad_disponible(),
        })
    return lineas


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
def devolver_venta(request, venta_id):
    venta = get_object_or_404(Venta.objects.select_related('vendedor'), id=venta_id)

    # lo que ya se devolvió de esta venta, con su motivo y lo que pasó con la unidad y el dinero
    historial = []
    registros = (Devolucion.objects.filter(detalle__venta=venta)
                 .select_related('detalle__producto', 'producto_entregado', 'vendedor')
                 .order_by('-fecha'))
    for dev in registros:
        historial.append({
            'dev': dev,
            'unidad': unidad_corta(dev.detalle.producto),
            'unidad_entregada': unidad_corta(dev.producto_entregado) if dev.producto_entregado else '',
        })

    return render(request, 'devolver_venta.html', {
        'venta': venta,
        'lineas': lineas_de_devolucion(venta),
        'historial': historial,
        'total_devuelto': venta.total_devuelto(),
        'total_neto': venta.total_neto(),
        'caja': caja_abierta(request.user),
    })


def validar_cantidad_devuelta(detalle, texto, unidad, disponible):
    """Revisa la cantidad que se devuelve. Devuelve (error, cantidad en la unidad base del producto)."""
    producto = detalle.producto
    try:
        cantidad = Decimal(texto.strip())
    except InvalidOperation:
        return 'La cantidad debe ser un número.', None
    if not cantidad.is_finite() or cantidad <= 0:
        return 'La cantidad debe ser un número mayor que 0.', None
    if producto.categoria.es_peso_variable and unidad not in ('g', 'kg'):
        return 'Elige la unidad del peso: gramos o kilos.', None

    cantidad = convertir_a_unidad_base(producto, cantidad, unidad)

    if cantidad.as_tuple().exponent < -3:
        return 'La cantidad es demasiado precisa (máximo 3 decimales en la unidad del producto).', None
    if not producto.categoria.es_peso_variable and cantidad != cantidad.to_integral_value():
        return 'Este producto se vende por unidades: ingresa un número entero.', None
    if cantidad > disponible:
        return (f'No se puede devolver más de lo vendido. De "{producto.nombre}" solo se puede devolver '
                f'{formats.localize(disponible.normalize())} {unidad_corta(producto)}.'), None
    return None, cantidad


@rol_requerido(Rol.VENDEDOR)
@caja_requerida
def devolver_producto(request, venta_id, detalle_id):
    venta = get_object_or_404(Venta, id=venta_id)
    detalle = get_object_or_404(DetalleVenta.objects.select_related('producto__categoria'),
                                id=detalle_id, venta=venta)
    caja = caja_abierta(request.user)
    errors = []
    # valores con los que arranca el formulario
    datos = {'resolucion': Devolucion.RESOLUCION_REEMBOLSO, 'forma_reembolso': Devolucion.FORMA_EFECTIVO}

    if request.method == 'POST':
        datos = request.POST

        with transaction.atomic():
            # se bloquea la línea mientras se guarda, para que dos devoluciones al mismo tiempo
            # no devuelvan más de lo vendido
            detalle = (DetalleVenta.objects.select_for_update()
                       .select_related('producto__categoria').get(id=detalle.id))
            producto = detalle.producto
            disponible = detalle.cantidad_disponible()
            caja = Caja.objects.select_for_update().filter(vendedor=request.user, abierta=True).first()
            if caja is None:
                messages.error(request, 'Primero debes abrir tu caja para registrar devoluciones.')
                return redirect('abrir_caja')

            # --- 1. cuánto se devuelve ---
            error, cantidad = validar_cantidad_devuelta(
                detalle, request.POST.get('cantidad', ''), request.POST.get('unidad', ''), disponible)
            if error:
                errors.append(error)

            # --- 2. por qué se devuelve ---
            motivo = request.POST.get('motivo', '')
            explicacion = request.POST.get('detalle_motivo', '').strip()
            reutilizable = request.POST.get('reutilizable', '')
            if motivo not in dict(Devolucion.MOTIVO_CHOICES):
                errors.append('Elige el motivo de la devolución.')
            if len(explicacion) > 300:
                errors.append('La explicación no puede tener más de 300 caracteres.')
            if motivo == Devolucion.MOTIVO_OTRO:
                if not explicacion:
                    errors.append('Cuando el motivo es "Otro", explica qué pasó.')
                if reutilizable not in ('si', 'no'):
                    errors.append('Indica si la unidad se puede volver a vender.')

            # --- 3. qué se hace con el cliente: reembolso o cambio por otro producto ---
            resolucion = request.POST.get('resolucion', '')
            forma = ''
            producto_entregado = None
            cantidad_entregada = None
            if resolucion == Devolucion.RESOLUCION_REEMBOLSO:
                forma = request.POST.get('forma_reembolso', '')
                if forma not in dict(Devolucion.FORMA_CHOICES):
                    errors.append('Elige cómo se devolvió el dinero: efectivo o transferencia.')
            elif resolucion == Devolucion.RESOLUCION_CAMBIO:
                entregado_id = request.POST.get('producto_entregado', '')
                if entregado_id.isdigit():
                    producto_entregado = Producto.objects.select_for_update().filter(
                        id=entregado_id, activo=True).first()
                if producto_entregado is None:
                    errors.append('Elige el producto que se entrega en el cambio.')
                else:
                    # mismas reglas que al vender: unidad, decimales y que alcance el stock
                    errores_entrega, cantidad_entregada = validar_cantidad(
                        producto_entregado, request.POST.get('cantidad_entregada', ''),
                        request.POST.get('unidad_entregada', ''))
                    errors.extend(f'Producto que se entrega: {e}' for e in errores_entrega)
            else:
                errors.append('Elige si se reembolsa el dinero o se cambia por otro producto.')

            if not errors:
                # --- el valor de lo devuelto, con el precio al que se vendió ---
                if cantidad == disponible:
                    # se devuelve todo lo que quedaba: se toma exactamente lo que faltaba por devolver,
                    # así no sobran ni faltan centavos por redondeo
                    valor = detalle.subtotal - detalle.valor_devuelto()
                else:
                    valor = calcular_subtotal(detalle.precio_unitario, cantidad)

                es_reembolso = resolucion == Devolucion.RESOLUCION_REEMBOLSO
                reembolso = valor if es_reembolso else Decimal('0')
                destino = destino_de_la_unidad(motivo, producto, reutilizable)

                # aviso (sin bloquear) si el efectivo que sale es más del que hay en la caja
                efectivo_en_caja = caja.efectivo_esperado()
                falta_efectivo = es_reembolso and forma == Devolucion.FORMA_EFECTIVO and reembolso > efectivo_en_caja

                Devolucion.objects.create(
                    detalle=detalle, cantidad=cantidad, valor=valor, vendedor=request.user, caja=caja,
                    motivo=motivo, detalle_motivo=explicacion, destino=destino,
                    resolucion=resolucion, forma_reembolso=forma, reembolso=reembolso,
                    producto_entregado=producto_entregado, cantidad_entregada=cantidad_entregada,
                )
                # 17A: la unidad vuelve al inventario solo si se puede volver a vender
                if destino == Devolucion.DESTINO_STOCK:
                    Producto.objects.filter(id=producto.id).update(stock=F('stock') + cantidad)
                # en un cambio, lo que se entrega sale del inventario
                if producto_entregado is not None:
                    Producto.objects.filter(id=producto_entregado.id).update(stock=F('stock') - cantidad_entregada)

                # 17B: el reembolso queda descontado del total vendido (Venta.total_neto) y, si se
                # devolvió en efectivo, también del efectivo esperado en la caja.
                que_paso_unidad = {
                    Devolucion.DESTINO_STOCK: 'La unidad volvió al inventario.',
                    Devolucion.DESTINO_CAMBIO: 'La unidad quedó para cambio con el proveedor.',
                    Devolucion.DESTINO_PERDIDA: 'La unidad se registró como pérdida.',
                }[destino]
                if es_reembolso:
                    como = 'en efectivo' if forma == Devolucion.FORMA_EFECTIVO else 'por transferencia'
                    que_paso_dinero = (f'Se reembolsaron ${formats.number_format(reembolso, decimal_pos=0, force_grouping=True)} '
                                       f'{como}.')
                else:
                    que_paso_dinero = (f'Se entregaron {formats.localize(cantidad_entregada.normalize())} '
                                       f'{unidad_corta(producto_entregado)} de "{producto_entregado.nombre}" '
                                       f'y el dinero no se movió.')
                messages.success(
                    request,
                    f'Devolución registrada: {formats.localize(cantidad.normalize())} {unidad_corta(producto)} '
                    f'de "{producto.nombre}". {que_paso_unidad} {que_paso_dinero}'
                )
                if falta_efectivo:
                    messages.warning(
                        request,
                        f'Ojo: devolviste ${formats.number_format(reembolso, decimal_pos=0, force_grouping=True)} en efectivo, '
                        f'pero según el sistema en tu caja hay ${formats.number_format(efectivo_en_caja, decimal_pos=0, force_grouping=True)}.'
                    )
                return redirect('devolver_venta', venta_id=venta.id)

    productos_cambio = [
        {'id': p.id, 'nombre': p.nombre, 'es_peso': p.categoria.es_peso_variable,
         'unidad': unidad_corta(p), 'stock': p.stock}
        for p in Producto.objects.filter(activo=True, stock__gt=0).select_related('categoria')
    ]
    return render(request, 'devolver_producto.html', {
        'venta': venta,
        'detalle': detalle,
        'producto': detalle.producto,
        'unidad': unidad_corta(detalle.producto),
        'es_peso': detalle.producto.categoria.es_peso_variable,
        'disponible': detalle.cantidad_disponible(),
        'motivos': Devolucion.MOTIVO_CHOICES,
        'productos_cambio': productos_cambio,
        'efectivo_en_caja': caja.efectivo_esperado() if caja else Decimal('0'),
        'errors': errors,
        'datos': datos,
    })


# ---------------------------------------------------------------
# HU19: historial de ventas (solo administrador)
# ---------------------------------------------------------------

PERIODOS = {'dia': 'Día', 'semana': 'Semana', 'mes': 'Mes'}


def rango_del_periodo(periodo, referencia):
    '''
    Devuelve (inicio, fin) del periodo que contiene la fecha de referencia.
    El inicio entra y el fin no entra: la semana va de lunes a domingo.
    '''
    if periodo == 'semana':
        inicio = referencia - timedelta(days=referencia.weekday())          # el lunes
        fin = inicio + timedelta(days=7)
    elif periodo == 'mes':
        inicio = referencia.replace(day=1)
        fin = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)   # primer día del mes siguiente
    else:
        inicio = referencia
        fin = inicio + timedelta(days=1)
    return inicio, fin


def leer_periodo(request):
    '''
    Lee ?periodo= y ?fecha= de la dirección y devuelve todo lo que necesitan las pantallas
    de historial y de reporte: el rango de fechas y los enlaces anterior / siguiente.
    '''
    hoy = timezone.localdate()

    periodo = request.GET.get('periodo', 'dia')
    if periodo not in PERIODOS:
        periodo = 'dia'
    try:
        referencia = date.fromisoformat(request.GET.get('fecha', ''))
    except ValueError:
        referencia = hoy
    if not 2000 <= referencia.year <= 2100:      # fechas absurdas: se vuelve a hoy
        referencia = hoy

    inicio, fin = rango_del_periodo(periodo, referencia)
    zona = timezone.get_current_timezone()
    return {
        'periodo': periodo,
        'periodos': PERIODOS,
        'referencia': referencia,
        'inicio': inicio,
        'ultimo_dia': fin - timedelta(days=1),
        'anterior': inicio - timedelta(days=1),   # cae dentro del periodo anterior
        'siguiente': fin,                          # es el primer día del periodo siguiente
        'hoy': hoy,
        'desde': datetime.combine(inicio, time.min, tzinfo=zona),
        'hasta': datetime.combine(fin, time.min, tzinfo=zona),
    }


@rol_requerido(Rol.ADMINISTRADOR)
def historial_ventas(request):
    p = leer_periodo(request)

    # 19A: las ventas del periodo elegido, de la más reciente a la más antigua
    ventas = (Venta.objects.filter(fecha__gte=p['desde'], fecha__lt=p['hasta'])
              .select_related('vendedor')
              .prefetch_related('detalles__producto__categoria')
              .order_by('-fecha'))

    # 17B: lo devuelto de cada venta, para mostrar el total neto (en una sola consulta)
    devuelto_por_venta = {
        fila['detalle__venta']: fila['total']
        for fila in (Devolucion.objects.filter(detalle__venta__in=ventas)
                     .order_by().values('detalle__venta').annotate(total=Sum('reembolso')))
    }

    filas = []
    total_vendido = Decimal('0')
    total_devuelto = Decimal('0')
    for venta in ventas:
        devuelto = devuelto_por_venta.get(venta.id, Decimal('0'))
        filas.append({
            'venta': venta,
            'lineas': [
                {'nombre': d.producto.nombre, 'cantidad': d.cantidad, 'unidad': unidad_corta(d.producto)}
                for d in venta.detalles.all()
            ],
            'devuelto': devuelto,
            'neto': venta.total - devuelto,
        })
        total_vendido += venta.total
        total_devuelto += devuelto

    # 19B: si no hay ventas, la plantilla muestra "no hay registros" (la lista llega vacía)
    return render(request, 'historial_ventas.html', {
        **p,
        'filas': filas,
        'cantidad': len(filas),
        'total_vendido': total_vendido,
        'total_devuelto': total_devuelto,
        'total_neto': total_vendido - total_devuelto,
    })


# ---------------------------------------------------------------
# HU20: reporte de ventas (solo administrador)
# ---------------------------------------------------------------

@rol_requerido(Rol.ADMINISTRADOR)
def reporte_ventas(request):
    p = leer_periodo(request)
    desde, hasta = p['desde'], p['hasta']

    # Todo se filtra por la fecha de la VENTA, igual que en el historial (HU19), así los
    # totales de las dos pantallas siempre coinciden.
    ventas = Venta.objects.filter(fecha__gte=desde, fecha__lt=hasta)
    detalles = DetalleVenta.objects.filter(venta__fecha__gte=desde, venta__fecha__lt=hasta)
    devoluciones = Devolucion.objects.filter(detalle__venta__fecha__gte=desde,
                                             detalle__venta__fecha__lt=hasta)

    # 20A: total vendido (bruto, devuelto y neto)
    resumen = ventas.aggregate(suma=Sum('total'), n=Count('id'))
    cantidad = resumen['n']
    total_vendido = resumen['suma'] or Decimal('0')
    total_devuelto = devoluciones.aggregate(suma=Sum('reembolso'))['suma'] or Decimal('0')
    total_neto = total_vendido - total_devuelto
    promedio = Decimal('0')
    if cantidad:
        promedio = (total_neto / cantidad).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 20B: los datos se agregan por producto; no se muestra transacción por transacción.
    # (Los nombres de las sumas no pueden llamarse igual que un campo del modelo.)
    vendido = (detalles.order_by()
               .values('producto_id', 'producto__nombre', 'producto__unidad_base',
                       'producto__categoria__es_peso_variable')
               .annotate(suma_cantidad=Sum('cantidad'), suma_valor=Sum('subtotal')))
    devuelto = {
        fila['detalle__producto_id']: fila
        for fila in (devoluciones.filter(resolucion=Devolucion.RESOLUCION_REEMBOLSO)
                     .order_by().values('detalle__producto_id')
                     .annotate(suma_cantidad=Sum('cantidad'), suma_valor=Sum('valor')))
    }

    ranking = []
    for fila in vendido:
        dev = devuelto.get(fila['producto_id'])
        cant = fila['suma_cantidad'] - (dev['suma_cantidad'] if dev else Decimal('0'))
        valor = fila['suma_valor'] - (dev['suma_valor'] if dev else Decimal('0'))
        if cant <= 0:
            continue                      # se devolvió todo: no cuenta como vendido
        if fila['producto__categoria__es_peso_variable']:
            unidad = 'kg' if fila['producto__unidad_base'] == Producto.UNIDAD_KILO else 'g'
        else:
            unidad = 'und'
        ranking.append({'nombre': fila['producto__nombre'], 'cantidad': cant,
                        'unidad': unidad, 'valor': valor})

    # Se comparan por valor vendido porque unos productos se miden en kg y otros en unidades.
    ranking.sort(key=lambda r: (-r['valor'], r['nombre']))
    maximo = ranking[0]['valor'] if ranking else Decimal('0')
    for r in ranking:
        r['porcentaje'] = max(2, int(r['valor'] * 100 / maximo)) if maximo > 0 else 0

    mas_vendido = ranking[0] if ranking else None
    menos_vendido = ranking[-1] if len(ranking) > 1 else None

    # Desglose por método de pago, también neto de devoluciones
    nombres = dict(Venta.METODO_PAGO_CHOICES)
    por_metodo = {}
    for fila in ventas.order_by().values('metodo_pago').annotate(n=Count('id'), suma=Sum('total')):
        por_metodo[fila['metodo_pago']] = {
            'nombre': nombres.get(fila['metodo_pago'], fila['metodo_pago']),
            'ventas': fila['n'], 'neto': fila['suma'],
        }
    for fila in (devoluciones.order_by().values('detalle__venta__metodo_pago')
                 .annotate(suma=Sum('reembolso'))):
        clave = fila['detalle__venta__metodo_pago']
        if clave in por_metodo:
            por_metodo[clave]['neto'] -= fila['suma']
    metodos = sorted(por_metodo.values(), key=lambda m: -m['neto'])

    return render(request, 'reporte_ventas.html', {
        **p,
        'cantidad': cantidad,
        'total_vendido': total_vendido,
        'total_devuelto': total_devuelto,
        'total_neto': total_neto,
        'promedio': promedio,
        'ranking': ranking,
        'mas_vendido': mas_vendido,
        'menos_vendido': menos_vendido,
        'metodos': metodos,
    })


# ---------------------------------------------------------------
# HU21: eliminar historial de ventas antiguo (solo administrador)
# ---------------------------------------------------------------

def rango_del_mes(anio, mes):
    """Devuelve (primer día, primer día del mes siguiente, y esos dos días como fecha y hora con zona)."""
    inicio = date(anio, mes, 1)
    _, fin = rango_del_periodo('mes', inicio)
    zona = timezone.get_current_timezone()
    return inicio, fin, datetime.combine(inicio, time.min, tzinfo=zona), datetime.combine(fin, time.min, tzinfo=zona)


def motivo_de_bloqueo(inicio, desde, hasta):
    """
    21D: dice por qué NO se puede eliminar ese mes, o devuelve None si se puede.
    Se protege lo que todavía está en uso: el mes actual (o uno futuro) y cualquier venta
    o devolución que pertenezca a una caja que sigue abierta, porque su efectivo esperado
    se calcula con ellas.
    """
    if inicio >= timezone.localdate().replace(day=1):
        return 'Es el mes actual (o uno futuro) y todavía está en uso.'
    if Venta.objects.filter(fecha__gte=desde, fecha__lt=hasta, caja__abierta=True).exists():
        return 'Tiene ventas de una caja que sigue abierta.'
    if Devolucion.objects.filter(detalle__venta__fecha__gte=desde, detalle__venta__fecha__lt=hasta,
                                 caja__abierta=True).exists():
        return 'Tiene devoluciones registradas en una caja que sigue abierta.'
    return None


def resumen_del_mes(desde, hasta):
    """Lo que se eliminaría de ese mes, para mostrarlo antes de confirmar."""
    ventas = Venta.objects.filter(fecha__gte=desde, fecha__lt=hasta).aggregate(n=Count('id'), suma=Sum('total'))
    return {
        'ventas': ventas['n'],
        'total': ventas['suma'] or Decimal('0'),
        'lineas': DetalleVenta.objects.filter(venta__fecha__gte=desde, venta__fecha__lt=hasta).count(),
        'devoluciones': Devolucion.objects.filter(detalle__venta__fecha__gte=desde,
                                                  detalle__venta__fecha__lt=hasta).count(),
    }


@rol_requerido(Rol.ADMINISTRADOR)
def eliminar_historial(request):
    # los meses que tienen ventas, del más reciente al más antiguo
    filas = (Venta.objects.annotate(mes=TruncMonth('fecha')).order_by()
             .values('mes').annotate(n=Count('id'), suma=Sum('total')).order_by('-mes'))
    meses = []
    for fila in filas:
        inicio = fila['mes'].date()
        _, _, desde, hasta = rango_del_mes(inicio.year, inicio.month)
        meses.append({
            'inicio': inicio,
            'ventas': fila['n'],
            'total': fila['suma'],
            'bloqueo': motivo_de_bloqueo(inicio, desde, hasta),
        })
    return render(request, 'eliminar_historial.html', {'meses': meses})


@rol_requerido(Rol.ADMINISTRADOR)
def confirmar_eliminar_historial(request, anio, mes):
    if not (2000 <= anio <= 2100 and 1 <= mes <= 12):
        raise Http404
    inicio, fin, desde, hasta = rango_del_mes(anio, mes)
    nombre_mes = formats.date_format(inicio, 'F \\d\\e Y')

    bloqueo = motivo_de_bloqueo(inicio, desde, hasta)
    if bloqueo:
        messages.error(request, f'No se puede eliminar el historial de {nombre_mes}: {bloqueo}')
        return redirect('eliminar_historial')

    resumen = resumen_del_mes(desde, hasta)
    if resumen['ventas'] == 0:
        messages.warning(request, f'{nombre_mes.capitalize()} no tiene ventas para eliminar.')
        return redirect('eliminar_historial')

    if request.method == 'POST':
        # 21C: solo se elimina si se contestó "Sí"; con cualquier otra respuesta no se toca nada
        if request.POST.get('confirmacion') != 'si':
            messages.warning(request, 'No se eliminó nada.')
            return redirect('eliminar_historial')

        # 21B: las ventas desaparecen, así que dejan de verse en el historial y en los reportes
        with transaction.atomic():
            bloqueo = motivo_de_bloqueo(inicio, desde, hasta)     # se revisa otra vez, por si cambió
            if bloqueo:
                messages.error(request, f'No se puede eliminar el historial de {nombre_mes}: {bloqueo}')
                return redirect('eliminar_historial')
            resumen = resumen_del_mes(desde, hasta)
            # el orden importa: las devoluciones protegen a las líneas de venta, así que van primero.
            # Al borrar las ventas se borran sus líneas. El inventario y las cajas no se tocan.
            Devolucion.objects.filter(detalle__venta__fecha__gte=desde, detalle__venta__fecha__lt=hasta).delete()
            Venta.objects.filter(fecha__gte=desde, fecha__lt=hasta).delete()

        messages.success(
            request,
            f'Se eliminó el historial de {nombre_mes}: {resumen["ventas"]} venta{"s" if resumen["ventas"] != 1 else ""}, '
            f'{resumen["lineas"]} línea{"s" if resumen["lineas"] != 1 else ""} de venta y '
            f'{resumen["devoluciones"]} devolución{"es" if resumen["devoluciones"] != 1 else ""}. '
            f'Los cierres de caja se conservaron.'
        )
        return redirect('eliminar_historial')

    return render(request, 'confirmar_eliminar_historial.html', {
        'inicio': inicio,
        'anio': anio,
        'mes': mes,
        'resumen': resumen,
    })


# ---------------------------------------------------------------
# HU25: productos para cambio y pérdidas (administrador o vendedor)
# ---------------------------------------------------------------

PERSONAL = (Rol.ADMINISTRADOR, Rol.VENDEDOR)
MOTIVOS_DE_BAJA = [
    (Devolucion.MOTIVO_VENCIDO, 'Producto vencido'),
    (Devolucion.MOTIVO_DEFECTUOSO, 'Defectuoso o daño de fábrica'),
    (Devolucion.MOTIVO_VICIO_OCULTO, 'Vicio oculto o daño no visible'),
    (Devolucion.MOTIVO_OTRO, 'Otro'),
]


def sincronizar_bajas_de_devoluciones():
    """
    25A: toda devolución cuya unidad no volvió al inventario (quedó "para cambio" o como pérdida)
    aparece sola en esta lista. Es seguro repetirla: cada devolución genera una sola baja.
    """
    nuevas = (Devolucion.objects.filter(destino__in=[Devolucion.DESTINO_CAMBIO, Devolucion.DESTINO_PERDIDA],
                                        baja__isnull=True)
              .select_related('detalle__producto', 'vendedor'))
    for dev in nuevas:
        estado = (RegistroBaja.ESTADO_PENDIENTE if dev.destino == Devolucion.DESTINO_CAMBIO
                  else RegistroBaja.ESTADO_PERDIDA)
        baja, creada = RegistroBaja.objects.get_or_create(devolucion=dev, defaults={
            'producto': dev.detalle.producto, 'cantidad': dev.cantidad, 'motivo': dev.motivo,
            'detalle_motivo': dev.detalle_motivo, 'estado': estado,
            'origen': RegistroBaja.ORIGEN_DEVOLUCION, 'registrada_por': dev.vendedor,
        })
        if creada:
            RegistroBaja.objects.filter(pk=baja.pk).update(fecha=dev.fecha)    # conserva la fecha de la devolución


def validar_cantidad_baja(producto, texto):
    """Devuelve (error, cantidad). Nunca se da de baja más de lo que hay en el inventario."""
    try:
        cantidad = Decimal(texto.strip())
    except InvalidOperation:
        return 'La cantidad debe ser un número.', None
    if not cantidad.is_finite() or cantidad <= 0:
        return 'La cantidad debe ser un número mayor que 0.', None
    if cantidad.as_tuple().exponent < -3:
        return 'La cantidad puede tener máximo 3 decimales.', None
    if not producto.categoria.es_peso_variable and cantidad != cantidad.to_integral_value():
        return 'Este producto se maneja por unidades: ingresa un número entero.', None
    if cantidad > producto.stock:
        return (f'Solo hay {formats.localize(producto.stock.normalize())} {unidad_corta(producto)} de '
                f'"{producto.nombre}" en el inventario.'), None
    return None, cantidad


@rol_requerido(*PERSONAL)
def lista_bajas(request):
    sincronizar_bajas_de_devoluciones()                                                     # 25A

    estado = request.GET.get('estado', '')
    bajas = RegistroBaja.objects.select_related(
        'producto__categoria', 'registrada_por', 'cambiada_por', 'devolucion__detalle')
    if estado in dict(RegistroBaja.ESTADO_CHOICES):                                         # 25F
        bajas = bajas.filter(estado=estado)

    conteos = {fila['estado']: fila['n']
               for fila in RegistroBaja.objects.order_by().values('estado').annotate(n=Count('id'))}
    return render(request, 'bajas_lista.html', {
        'filas': [{'baja': b, 'unidad': unidad_corta(b.producto)} for b in bajas],
        'estado': estado,
        'total': sum(conteos.values()),
        'pendientes': conteos.get(RegistroBaja.ESTADO_PENDIENTE, 0),
        'cambiadas': conteos.get(RegistroBaja.ESTADO_CAMBIADO, 0),
        'perdidas': conteos.get(RegistroBaja.ESTADO_PERDIDA, 0),
    })


@rol_requerido(*PERSONAL)
def registrar_baja(request):
    errors = []
    datos = {}

    if request.method == 'POST':
        datos = request.POST
        producto_id = request.POST.get('producto', '')
        motivo = request.POST.get('motivo', '')
        detalle = request.POST.get('detalle_motivo', '').strip()

        if not producto_id.isdigit() or not Producto.objects.filter(id=producto_id, activo=True).exists():
            errors.append('Elige el producto.')
        if motivo not in dict(MOTIVOS_DE_BAJA):
            errors.append('Elige el motivo.')
        elif motivo == Devolucion.MOTIVO_OTRO and not detalle:
            errors.append('Cuando el motivo es "Otro", explica qué pasó.')
        if len(detalle) > 300:
            errors.append('La explicación no puede tener más de 300 caracteres.')

        if not errors:
            with transaction.atomic():
                # se bloquea el producto para revisar y descontar el stock sin que otro lo cambie
                producto = Producto.objects.select_for_update().select_related('categoria').get(id=producto_id)
                error, cantidad = validar_cantidad_baja(producto, request.POST.get('cantidad', ''))
                if error:
                    errors.append(error)
                else:
                    # 25B: sale del inventario disponible
                    Producto.objects.filter(id=producto.id).update(stock=F('stock') - cantidad)
                    # 25C y 25E: si el proveedor recibe cambios queda pendiente; si no, es pérdida
                    estado = (RegistroBaja.ESTADO_PENDIENTE if producto.recibe_cambio
                              else RegistroBaja.ESTADO_PERDIDA)
                    RegistroBaja.objects.create(
                        producto=producto, cantidad=cantidad, motivo=motivo, detalle_motivo=detalle,
                        estado=estado, origen=RegistroBaja.ORIGEN_INVENTARIO, registrada_por=request.user)
                    queda = ('Quedó pendiente de cambio con el proveedor.'
                             if estado == RegistroBaja.ESTADO_PENDIENTE
                             else 'Este producto no recibe cambio, así que se registró como pérdida.')
                    messages.success(
                        request,
                        f'Baja registrada: {formats.localize(cantidad.normalize())} {unidad_corta(producto)} '
                        f'de "{producto.nombre}" salieron del inventario. {queda}')
                    return redirect('lista_bajas')

    productos = [
        {'id': p.id, 'nombre': p.nombre, 'unidad': unidad_corta(p), 'stock': p.stock, 'recibe_cambio': p.recibe_cambio}
        for p in Producto.objects.filter(activo=True, stock__gt=0).select_related('categoria')
    ]
    return render(request, 'baja_form.html', {
        'productos': productos, 'motivos': MOTIVOS_DE_BAJA, 'errors': errors, 'datos': datos,
    })


@rol_requerido(*PERSONAL)
@require_POST
def marcar_baja_cambiada(request, baja_id):
    with transaction.atomic():
        baja = get_object_or_404(RegistroBaja.objects.select_for_update(), id=baja_id)
        if baja.estado != RegistroBaja.ESTADO_PENDIENTE:
            messages.error(request, 'Esta baja no está pendiente de cambio.')
        else:
            baja.estado = RegistroBaja.ESTADO_CAMBIADO                                      # 25D
            baja.cambiada_en = timezone.now()
            baja.cambiada_por = request.user
            baja.save(update_fields=['estado', 'cambiada_en', 'cambiada_por'])
            messages.success(
                request,
                'Marcada como cambiada. Si el proveedor te entregó unidades nuevas, ingrésalas '
                'en una recepción de mercancía.')
    return redirect('lista_bajas')