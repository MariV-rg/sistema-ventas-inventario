from django.urls import path
from . import views

urlpatterns = [
    path('usuarios/registrar/', views.registrar_usuario, name='registrar_usuario'),
]