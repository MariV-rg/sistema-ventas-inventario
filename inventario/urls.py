from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/nuevo/', views.registrar_producto, name='registrar_producto'),
    path('productos/<int:id>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:id>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
    path('inventario/', views.consultar_inventario, name='consultar_inventario'),
    path('inventario/alertas/', views.alertas_stock, name='alertas_stock'),
    path('inventario/<int:id>/ingresar/', views.ingresar_unidades, name='ingresar_unidades'),
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/nueva/', views.crear_categoria, name='crear_categoria'),
    path('categorias/<int:id>/editar/', views.editar_categoria, name='editar_categoria'),
    path('categorias/<int:id>/eliminar/', views.eliminar_categoria, name='eliminar_categoria'),
    path('recepciones/', views.lista_recepciones, name='lista_recepciones'),
    path('recepciones/nueva/', views.crear_recepcion, name='crear_recepcion'),
    path('recepciones/<int:id>/', views.detalle_recepcion, name='detalle_recepcion'),
    path('recepciones/<int:id>/agregar/', views.agregar_linea_recepcion, name='agregar_linea_recepcion'),
    path('recepciones/<int:id>/lineas/<int:linea_id>/ingresar/', views.ingresar_linea_recepcion, name='ingresar_linea_recepcion'),
    path('recepciones/<int:id>/lineas/<int:linea_id>/quitar/', views.quitar_linea_recepcion, name='quitar_linea_recepcion'),
]