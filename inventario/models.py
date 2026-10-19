from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


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

    nombre = models.CharField(max_length=100, unique=True)          # 5C: sin duplicados
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='productos')
    precio = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    unidad_base = models.CharField(max_length=10, choices=UNIDAD_BASE_CHOICES, blank=True)  # 5D / 5E
    stock = models.DecimalField(max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)])  # lo usan HU9-HU11
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)])  # 5F
    activo = models.BooleanField(default=True)                      # HU7: "eliminar" = poner activo=False
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

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

class Caja(models.Model):
    '''
    Caja del vendedor (HU12). Al abrirla se guarda el monto inicial del turno,
    que sirve de base de comparación al cerrar.
    '''
    ESTADO_ABIERTA = 'ABIERTA'
    ESTADO_CERRADA = 'CERRADA'
    ESTADO_CHOICES = [
        (ESTADO_ABIERTA, 'Abierta'),
        (ESTADO_CERRADA, 'Cerrada'),
    ]

    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cajas',
    )
    monto_inicial = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='Monto inicial',
    )
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default=ESTADO_ABIERTA,
    )

    class Meta:
        ordering = ['-fecha_apertura']

    def __str__(self):
        return f'Caja de {self.vendedor} ({self.get_estado_display()})'