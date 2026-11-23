from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Perfil, Rol

from .models import Categoria, Producto


class CategoriasTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('principal', password='Tienda-Segura-2026')
        self.client.force_login(self.admin)

    def test_la_lista_muestra_las_categorias(self):
        # 23A
        respuesta = self.client.get(reverse('lista_categorias'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context['categorias']), Categoria.objects.count())

    def test_crear_una_categoria(self):
        # 23B
        self.client.post(reverse('crear_categoria'), {'nombre': 'Lácteos', 'es_peso_variable': 'on'})
        categoria = Categoria.objects.get(nombre='Lácteos')
        self.assertTrue(categoria.es_peso_variable)

    def test_no_se_crea_con_nombre_repetido_sin_importar_mayusculas_ni_tildes(self):
        # 23C
        Categoria.objects.create(nombre='Frutería')
        antes = Categoria.objects.count()
        self.client.post(reverse('crear_categoria'), {'nombre': 'FRUTERIA'})
        self.assertEqual(Categoria.objects.count(), antes)

    def test_no_se_crea_con_nombre_vacio(self):
        # 23C
        antes = Categoria.objects.count()
        self.client.post(reverse('crear_categoria'), {'nombre': '   '})
        self.assertEqual(Categoria.objects.count(), antes)

    def test_editar_el_nombre(self):
        # 23D
        categoria = Categoria.objects.create(nombre='Dulces')
        self.client.post(reverse('editar_categoria', args=[categoria.id]), {'nombre': 'Golosinas'})
        categoria.refresh_from_db()
        self.assertEqual(categoria.nombre, 'Golosinas')

    def test_no_se_puede_cambiar_si_se_vende_por_peso_cuando_ya_tiene_productos(self):
        # 23E
        categoria = Categoria.objects.create(nombre='Verduras', es_peso_variable=True)
        Producto.objects.create(categoria=categoria, nombre='Zanahoria', precio=Decimal('2000'), stock=Decimal('5'))
        # se manda el formulario sin la casilla marcada: intenta pasar a "por unidad"
        self.client.post(reverse('editar_categoria', args=[categoria.id]), {'nombre': 'Verduras'})
        categoria.refresh_from_db()
        self.assertTrue(categoria.es_peso_variable)

    def test_eliminar_una_categoria_sin_productos(self):
        # 23F
        categoria = Categoria.objects.create(nombre='Temporal')
        self.client.post(reverse('eliminar_categoria', args=[categoria.id]))
        self.assertFalse(Categoria.objects.filter(id=categoria.id).exists())

    def test_no_se_elimina_una_categoria_con_productos(self):
        # 23F
        categoria = Categoria.objects.create(nombre='Con productos')
        Producto.objects.create(categoria=categoria, nombre='Algo', precio=Decimal('1000'), stock=Decimal('1'))
        self.client.post(reverse('eliminar_categoria', args=[categoria.id]))
        self.assertTrue(Categoria.objects.filter(id=categoria.id).exists())

    def test_un_vendedor_no_puede_gestionar_categorias(self):
        vendedor = User.objects.create_user('vend', password='Tienda-Segura-2026')
        Perfil.objects.create(usuario=vendedor).roles.set([Rol.objects.get(nombre=Rol.VENDEDOR)])
        self.client.force_login(vendedor)
        self.assertEqual(self.client.get(reverse('lista_categorias')).status_code, 302)
        antes = Categoria.objects.count()
        self.client.post(reverse('crear_categoria'), {'nombre': 'Intruso'})
        self.assertEqual(Categoria.objects.count(), antes)