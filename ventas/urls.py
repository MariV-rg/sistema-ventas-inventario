from django.urls import path
from . import views

urlpatterns = [
    path('ventas/caja/abrir/', views.abrir_caja, name='abrir_caja'),
    path('ventas/caja/cerrar/', views.cerrar_caja, name='cerrar_caja'),
    path('ventas/caja/<int:caja_id>/resultado/', views.resultado_cierre, name='resultado_cierre'),
    path('ventas/nueva/', views.nueva_venta, name='nueva_venta'),
    path('ventas/agregar/', views.agregar_al_carrito, name='agregar_al_carrito'),
    path('ventas/<int:producto_id>/actualizar/', views.actualizar_carrito, name='actualizar_carrito'),
    path('ventas/<int:producto_id>/quitar/', views.quitar_del_carrito, name='quitar_del_carrito'),
    path('ventas/revisar/', views.revisar_venta, name='revisar_venta'),
    path('ventas/confirmar/', views.confirmar_venta, name='confirmar_venta'),
    path('ventas/cancelar/', views.cancelar_venta, name='cancelar_venta'),
    path('ventas/devoluciones/', views.devoluciones, name='devoluciones'),
    path('ventas/devoluciones/<int:venta_id>/', views.devolver_venta, name='devolver_venta'),
    path('ventas/devoluciones/<int:venta_id>/registrar/', views.registrar_devolucion, name='registrar_devolucion'),
]