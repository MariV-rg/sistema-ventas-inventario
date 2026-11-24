from django.urls import path
from . import views

urlpatterns = [
    path('usuarios/registrar/', views.registrar_usuario, name='registrar_usuario'),
    path('configuracion-inicial/', views.configuracion_inicial, name='configuracion_inicial'),
]