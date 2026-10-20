from django.contrib import admin

from .models import Caja, DetalleVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'vendedor', 'metodo_pago', 'total', 'caja')
    list_filter = ('metodo_pago',)
    inlines = [DetalleVentaInline]


@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'vendedor', 'fecha_apertura', 'monto_inicial', 'abierta')
    list_filter = ('abierta',)