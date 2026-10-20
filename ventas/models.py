from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q, UniqueConstraint

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

    # HU18 (cierre de caja): aquí se agregan la fecha de cierre, el monto final contado
    # y el descuadre. El efectivo esperado = monto_inicial + ventas en efectivo de esta caja.

    class Meta:
        ordering = ['-fecha_apertura']
        constraints = [
            # la base de datos también impide tener dos cajas abiertas del mismo vendedor
            UniqueConstraint(fields=['vendedor'], condition=Q(abierta=True),
                             name='una_caja_abierta_por_vendedor'),
        ]

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

    def __str__(self):
        return f'{self.cantidad} x {self.producto.nombre}'