from django.contrib import admin
from .models import Categoria, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'es_peso_variable')


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio', 'unidad_base', 'stock', 'stock_minimo', 'activo')
    list_filter = ('categoria', 'activo')
    search_fields = ('nombre',)