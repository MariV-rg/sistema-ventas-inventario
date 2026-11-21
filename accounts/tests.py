from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import RegistroUsuarioForm
from .models import Perfil, Rol


class RolesAutomaticosTests(TestCase):
    def test_los_roles_existen_sin_crearlos_a_mano(self):
        # 29A: la migración los crea, así que existen en una base de datos nueva
        self.assertTrue(Rol.objects.filter(nombre=Rol.ADMINISTRADOR).exists())
        self.assertTrue(Rol.objects.filter(nombre=Rol.VENDEDOR).exists())


class AdministradorPrincipalTests(TestCase):
    def setUp(self):
        self.rol_admin = Rol.objects.get(nombre=Rol.ADMINISTRADOR)
        self.rol_vendedor = Rol.objects.get(nombre=Rol.VENDEDOR)

        self.principal = User.objects.create_superuser('principal', password='Tienda-Segura-2026')
        self.admin = User.objects.create_user('admin', password='Tienda-Segura-2026')
        Perfil.objects.create(usuario=self.admin).roles.set([self.rol_admin])

        self.url = reverse('registrar_usuario')

    def datos(self, username, roles):
        return {
            'username': username,
            'password1': 'Tienda-Segura-2026',
            'password2': 'Tienda-Segura-2026',
            'roles': [r.id for r in roles],
        }

    def test_el_principal_puede_asignar_cualquier_rol(self):
        # 29B
        form = RegistroUsuarioForm(quien_registra=self.principal)
        self.assertEqual(set(form.fields['roles'].queryset), {self.rol_admin, self.rol_vendedor})

    def test_el_administrador_comun_solo_ve_el_rol_vendedor(self):
        # 29C
        form = RegistroUsuarioForm(quien_registra=self.admin)
        self.assertEqual(list(form.fields['roles'].queryset), [self.rol_vendedor])

    def test_el_principal_crea_un_administrador(self):
        self.client.force_login(self.principal)
        self.client.post(self.url, self.datos('nuevo_admin', [self.rol_admin]))
        nuevo = User.objects.get(username='nuevo_admin')
        self.assertTrue(nuevo.perfil.tiene_rol(Rol.ADMINISTRADOR))

    def test_el_administrador_comun_no_puede_crear_administradores(self):
        # 29D: aunque mande el rol a la fuerza, no se crea el usuario
        self.client.force_login(self.admin)
        self.client.post(self.url, self.datos('intruso', [self.rol_admin]))
        self.assertFalse(User.objects.filter(username='intruso').exists())

    def test_el_administrador_comun_si_puede_crear_vendedores(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.datos('nuevo_vendedor', [self.rol_vendedor]))
        nuevo = User.objects.get(username='nuevo_vendedor')
        self.assertTrue(nuevo.perfil.tiene_rol(Rol.VENDEDOR))
        self.assertFalse(nuevo.perfil.tiene_rol(Rol.ADMINISTRADOR))


class ConfiguracionInicialTests(TestCase):
    def datos(self, username='principal'):
        return {
            'username': username,
            'email': 'principal@tienda.com',
            'password1': 'Tienda-Segura-2026',
            'password2': 'Tienda-Segura-2026',
        }

    def test_sin_usuarios_el_login_lleva_a_la_configuracion_inicial(self):
        # 29F
        respuesta = self.client.get(reverse('login'))
        self.assertRedirects(respuesta, reverse('configuracion_inicial'))

    def test_se_crea_el_administrador_principal(self):
        respuesta = self.client.post(reverse('configuracion_inicial'), self.datos())
        self.assertRedirects(respuesta, reverse('home'), fetch_redirect_response=False)
        principal = User.objects.get(username='principal')
        self.assertTrue(principal.is_superuser)
        self.assertTrue(principal.perfil.tiene_rol(Rol.ADMINISTRADOR))

    def test_con_usuarios_existentes_la_configuracion_no_esta_permitida(self):
        # 29G
        User.objects.create_user('alguien', password='Tienda-Segura-2026')
        respuesta = self.client.get(reverse('configuracion_inicial'))
        self.assertRedirects(respuesta, reverse('login'))
        self.client.post(reverse('configuracion_inicial'), self.datos('intruso'))
        self.assertFalse(User.objects.filter(username='intruso').exists())

    def test_con_usuarios_existentes_el_login_funciona_normal(self):
        User.objects.create_user('alguien', password='Tienda-Segura-2026')
        respuesta = self.client.get(reverse('login'))
        self.assertEqual(respuesta.status_code, 200)