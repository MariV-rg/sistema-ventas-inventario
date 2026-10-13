from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/nuevo/', views.registrar_producto, name='registrar_producto'),
    path('productos/<int:id>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:id>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
]