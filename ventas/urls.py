from django.urls import path
from . import views

urlpatterns = [
    path('ventas/nueva/', views.nueva_venta, name='nueva_venta'),
    path('ventas/agregar/', views.agregar_al_carrito, name='agregar_al_carrito'),
    path('ventas/<int:producto_id>/actualizar/', views.actualizar_carrito, name='actualizar_carrito'),
    path('ventas/<int:producto_id>/quitar/', views.quitar_del_carrito, name='quitar_del_carrito'),
    path('ventas/confirmar/', views.confirmar_venta, name='confirmar_venta'),
]