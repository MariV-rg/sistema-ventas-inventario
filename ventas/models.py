from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q, Sum, UniqueConstraint
from django.utils import timezone

from inventario.models import Producto


class Caja(models.Model):
    '''
    La caja de un vendedor (HU12). Cada vendedor abre su propia caja al empezar el turno,
    con un monto inicial. Un vendedor solo puede tener una caja abierta a la vez, y sin
    su caja abierta no puede vender.
    '''
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cajas')   # dueño de la caja
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    monto_inicial = models.DecimalField(max_digits=12, decimal_places=2)                  # base de apertura
    abierta = models.BooleanField(default=True)

    # HU18 (cierre de caja): se llenan cuando el vendedor cierra su caja
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_final = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)     # lo que contó
    monto_esperado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # lo que calculó el sistema
    diferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)      # contado - esperado

    class Meta:
        ordering = ['-fecha_apertura']
        constraints = [
            # la base de datos también impide tener dos cajas abiertas del mismo vendedor
            UniqueConstraint(fields=['vendedor'], condition=Q(abierta=True),
                             name='una_caja_abierta_por_vendedor'),
        ]

    def ventas_en_efectivo(self):
        '''14K: lo vendido en efectivo en esta caja (esto sí entra a la caja).'''
        total = self.ventas.filter(metodo_pago=Venta.EFECTIVO).aggregate(total=Sum('total'))['total']
        return total or Decimal('0')

    def ventas_por_otros_medios(self):
        '''14J: lo vendido por Nequi, Daviplata, Bancolombia u otro (no entra a la caja).'''
        total = self.ventas.exclude(metodo_pago=Venta.EFECTIVO).aggregate(total=Sum('total'))['total']
        return total or Decimal('0')

    def devoluciones_en_efectivo(self):
        '''HU17: lo devuelto en efectivo en esta caja (sale de la caja). Las devoluciones de ventas
        pagadas por Nequi, Daviplata, etc. no mueven el efectivo.'''
        total = self.devoluciones.filter(detalle__venta__metodo_pago=Venta.EFECTIVO).aggregate(total=Sum('valor'))['total']
        return total or Decimal('0')

    def efectivo_esperado(self):
        '''Lo que debería haber en la caja: monto inicial + ventas en efectivo - devoluciones en efectivo
        (la HU18 lo compara al cerrar).'''
        return self.monto_inicial + self.ventas_en_efectivo() - self.devoluciones_en_efectivo()

    def diferencia_absoluta(self):
        '''El descuadre sin signo, para mostrarlo: "Sobran $X" o "Faltan $X".'''
        return abs(self.diferencia) if self.diferencia is not None else Decimal('0')

    def cerrar(self, monto_final):
        '''
        18A: cierra la caja. Compara lo que el vendedor contó con lo esperado por el sistema
        (monto inicial + ventas en efectivo) y guarda el resultado.
        18B: diferencia positiva = sobra dinero (a favor); negativa = falta dinero (en contra).
        '''
        self.monto_esperado = self.efectivo_esperado()
        self.monto_final = monto_final
        self.diferencia = monto_final - self.monto_esperado
        self.fecha_cierre = timezone.now()
        self.abierta = False
        self.save()

    def __str__(self):
        return f'Caja #{self.id}'


class Venta(models.Model):
    '''
    Una venta ya confirmada (HU14). Guarda quién vendió, cuándo, cómo pagó y el total.
    El detalle (qué productos y cuántos) está en DetalleVenta.
    '''
    EFECTIVO = 'EFECTIVO'
    NEQUI = 'NEQUI'
    DAVIPLATA = 'DAVIPLATA'
    BANCOLOMBIA = 'BANCOLOMBIA'
    OTRO = 'OTRO'
    METODO_PAGO_CHOICES = [
        (EFECTIVO, 'Efectivo'),
        (NEQUI, 'Nequi'),
        (DAVIPLATA, 'Daviplata'),
        (BANCOLOMBIA, 'Bancolombia'),
        (OTRO, 'Otro'),
    ]

    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ventas')
    fecha = models.DateTimeField(auto_now_add=True)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)   # 14I
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # HU12: la caja del vendedor que estaba abierta cuando se hizo la venta. Sirve para que HU18 sume
    # solo las ventas en efectivo de esa caja (14J y 14K). Es opcional (null) porque
    # pueden existir ventas hechas antes de que existiera la caja.
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name='ventas',
                             null=True, blank=True)

    class Meta:
        ordering = ['-fecha']

    def total_devuelto(self):
        '''HU17: suma de lo devuelto de esta venta.'''
        total = Devolucion.objects.filter(detalle__venta=self).aggregate(total=Sum('valor'))['total']
        return total or Decimal('0')

    def total_neto(self):
        '''HU17B: lo que realmente quedó vendido (total - devoluciones). Es el valor que deben usar
        el historial y los reportes.'''
        return self.total - self.total_devuelto()

    def __str__(self):
        return f'Venta #{self.id}'


class DetalleVenta(models.Model):
    '''
    Una línea de la venta: un producto con su cantidad.
    El precio se guarda tal como estaba al vender, para que el historial (HU19)
    no cambie si después se edita el precio del producto.
    '''
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='detalles_venta')
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)       # en la unidad base del producto
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)  # precio por unidad base
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def cantidad_devuelta(self):
        total = self.devoluciones.aggregate(total=Sum('cantidad'))['total']
        return total or Decimal('0')

    def cantidad_disponible(self):
        '''Lo que todavía se puede devolver de esta línea.'''
        return self.cantidad - self.cantidad_devuelta()

    def valor_devuelto(self):
        total = self.devoluciones.aggregate(total=Sum('valor'))['total']
        return total or Decimal('0')

    def __str__(self):
        return f'{self.cantidad} x {self.producto.nombre}'


class Devolucion(models.Model):
    '''
    HU17: devolución de un producto de una venta ya confirmada.
    La cantidad vuelve al inventario y el valor se descuenta del total vendido.
    Se guarda en una tabla aparte para no alterar la venta original (queda el rastro).
    '''
    detalle = models.ForeignKey(DetalleVenta, on_delete=models.PROTECT, related_name='devoluciones')
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)       # en la unidad base del producto
    valor = models.DecimalField(max_digits=12, decimal_places=2)          # lo que se descuenta del total vendido
    fecha = models.DateTimeField(auto_now_add=True)
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='devoluciones')
    # la caja que estaba abierta al devolver: si la venta fue en efectivo, el dinero sale de esa caja
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name='devoluciones',
                             null=True, blank=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f'Devolución #{self.id}'