from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('productos/nuevo/', views.registrar_producto, name='registrar_producto'),
]