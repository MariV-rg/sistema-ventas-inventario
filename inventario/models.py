from django.db import models

class Categoria(models.Model):
    '''Categoría del producto (HU8): Aseo, Plaza, Licor,SNacks, Mercado, etc.
    es_peso_variable indica si los productos de esta categgoría se venden por peso (ej. Plaza) o por unidad (ej. Aseo).
    '''
    nombre = models.CharField(max_length=50, unique=True)
    es_peso_variable = models.BooleanField(
        default=False,
        verbose_name='¿Se vende por peso?',
        help_text='Actívaalo para categorias como Plza (papa, cebolla, tomate...)'
    )

    class Meta:
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    '''
    Calogo de productos (HU5). Cubre unidad fija y peso variable segun a la categoría a la que pertenezca.
    '''

    UNIDAD_KILO = 'KILO'
    UNIDAD_LITRO = 'LITRO'