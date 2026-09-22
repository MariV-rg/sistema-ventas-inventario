from .models import Rol
from .views import es_administrador


def roles(request):
    '''
    Le mete a cada plantilla las variables es_admin / es_vendedor,
    para poder ocultar botones o links según el rol sin repetir código
    en cada vista (HU4 - 4B).
    '''
    if not request.user.is_authenticated:
        return {}

    perfil = getattr(request.user, 'perfil', None)
    es_vendedor = request.user.is_superuser or (perfil and perfil.tiene_rol(Rol.VENDEDOR))

    return {
        'es_admin': es_administrador(request.user),
        'es_vendedor': bool(es_vendedor),
    }