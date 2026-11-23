from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from accounts.views import LoginConConfiguracionInicial

urlpatterns = [
    path('', include('inventario.urls')),
    path('', include('accounts.urls')),
    path('', include('ventas.urls')),
    path('admin/', admin.site.urls),
    path('login/', LoginConConfiguracionInicial.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
