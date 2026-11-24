from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class Categoria(models.Model):
    '''
    Categoría del catálogo (HU8): Aseo, Plaza, Licor, Snacks, Mercado, etc.
    es_peso_variable indica si los productos de la categoría se venden por peso
    (ej. Plaza: papa, cebolla) o por unidad (ej. Aseo, Licor).
    '''
    nombre = models.CharField(max_length=50, unique=True)
    es_peso_variable = models.BooleanField(
        default=False,
        verbose_name='¿Se vende por peso?',
        help_text='Actívalo para categorías como Plaza (papa, cebolla, tomate...).',
    )

    class Meta:
        verbose_name_plural = 'Categorías'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    '''
    Producto del catálogo (HU5). La categoría decide si se maneja por peso
    (pide unidad base) o por unidad (no la pide).
    '''
    UNIDAD_KILO = 'KILO'
    UNIDAD_GRAMO = 'GRAMO'
    UNIDAD_BASE_CHOICES = [
        (UNIDAD_KILO, 'Kilo'),
        (UNIDAD_GRAMO, 'Gramo'),
    ]

    nombre = models.CharField(max_length=100)                       # 5C: sin duplicados entre los activos (ver Meta)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='productos')
    precio = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    unidad_base = models.CharField(max_length=10, choices=UNIDAD_BASE_CHOICES, blank=True)  # 5D / 5E
    stock = models.DecimalField(max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)])  # lo usan HU9-HU11
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)])  # 5F
    activo = models.BooleanField(default=True)                      # HU7: "eliminar" = poner activo=False
    # HU17: si el proveedor recibe cambios cuando el producto llega vencido o defectuoso
    recibe_cambio = models.BooleanField(
        default=False,
        verbose_name='¿El proveedor recibe cambios?',
        help_text='Márcalo en productos que el proveedor cambia si llegan vencidos o defectuosos (ej. yogures).',
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        constraints = [
            # el nombre no se repite entre los productos activos (el de uno eliminado queda libre)
            models.UniqueConstraint(fields=['nombre'], condition=Q(activo=True), name='producto_nombre_unico_entre_activos'),
        ]

    def clean(self):
        if not self.categoria_id:
            return
        if self.categoria.es_peso_variable and not self.unidad_base:
            raise ValidationError({
                'unidad_base': 'Esta categoría se vende por peso: elige la unidad base (kilo o gramo).'
            })
        if not self.categoria.es_peso_variable:
            self.unidad_base = ''   # 5E: por unidad no lleva unidad base

    def __str__(self):
        return self.nombre


class Recepcion(models.Model):
    '''
    HU24: la mercancía que llega de un proveedor, registrada contra su factura.
    Sirve para saber qué productos de esa factura ya se ingresaron al inventario y cuáles faltan,
    y así no ingresarlos dos veces.
    '''
    proveedor = models.CharField(max_length=100)
    numero_factura = models.CharField(max_length=50)
    fecha = models.DateField()
    registrada_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recepciones')
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creada_en']
        constraints = [
            # 24B: la misma factura no se registra dos veces para el mismo proveedor
            models.UniqueConstraint(fields=['proveedor', 'numero_factura'], name='recepcion_factura_unica_por_proveedor'),
        ]

    def total_lineas(self):
        return self.lineas.count()

    def lineas_ingresadas(self):
        return self.lineas.filter(ingresada=True).count()

    def esta_completa(self):
        total = self.total_lineas()
        return total > 0 and self.lineas_ingresadas() == total

    def __str__(self):
        return f'{self.proveedor} · factura {self.numero_factura}'


class LineaRecepcion(models.Model):
    '''Un producto de la factura, con la cantidad que debe llegar. Pendiente hasta que se ingresa.'''
    recepcion = models.ForeignKey(Recepcion, on_delete=models.CASCADE, related_name='lineas')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='lineas_recepcion')
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)       # en la unidad base del producto
    ingresada = models.BooleanField(default=False)
    ingresada_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='lineas_ingresadas',
                                      null=True, blank=True)
    ingresada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            # un producto aparece una sola vez por factura: así no se duplican las unidades
            models.UniqueConstraint(fields=['recepcion', 'producto'], name='linea_producto_unico_por_recepcion'),
        ]

    def __str__(self):
        return f'{self.cantidad} x {self.producto.nombre}'