from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Perfil, Rol

from .models import Categoria, LineaRecepcion, Producto, Recepcion


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


class RecepcionTests(TestCase):
    def setUp(self):
        self.vendedor = User.objects.create_user('vend', password='Tienda-Segura-2026')
        Perfil.objects.create(usuario=self.vendedor).roles.set([Rol.objects.get(nombre=Rol.VENDEDOR)])
        self.client.force_login(self.vendedor)           # 24H: lo puede hacer el personal, no solo el administrador

        categoria, _ = Categoria.objects.get_or_create(nombre='Aseo')
        self.jabon = Producto.objects.create(categoria=categoria, nombre='Jabón', precio=Decimal('2000'), stock=Decimal('10'))
        self.cloro = Producto.objects.create(categoria=categoria, nombre='Cloro', precio=Decimal('3000'), stock=Decimal('5'))

    def crear(self, proveedor='Alpina', factura='FV-1'):
        return Recepcion.objects.create(proveedor=proveedor, numero_factura=factura,
                                        fecha=timezone.localdate(), registrada_por=self.vendedor)

    def agregar(self, recepcion, producto, cantidad):
        return self.client.post(reverse('agregar_linea_recepcion', args=[recepcion.id]),
                                {'producto': producto.id, 'cantidad': cantidad})

    def ingresar(self, linea):
        return self.client.post(reverse('ingresar_linea_recepcion', args=[linea.recepcion_id, linea.id]))

    def test_crear_una_recepcion(self):
        # 24A
        self.client.post(reverse('crear_recepcion'), {
            'proveedor': 'Alpina', 'numero_factura': 'FV-4532', 'fecha': timezone.localdate().isoformat()})
        recepcion = Recepcion.objects.get(numero_factura='FV-4532')
        self.assertEqual(recepcion.proveedor, 'Alpina')
        self.assertEqual(recepcion.registrada_por, self.vendedor)

    def test_la_misma_factura_del_mismo_proveedor_no_se_registra_dos_veces(self):
        # 24B (sin importar mayúsculas)
        self.crear('Alpina', 'FV-1')
        respuesta = self.client.post(reverse('crear_recepcion'), {
            'proveedor': 'ALPINA', 'numero_factura': 'fv-1', 'fecha': timezone.localdate().isoformat()})
        self.assertEqual(Recepcion.objects.count(), 1)
        self.assertIsNotNone(respuesta.context['existente'])

    def test_el_mismo_numero_de_factura_de_otro_proveedor_si_se_permite(self):
        self.crear('Alpina', 'FV-1')
        self.client.post(reverse('crear_recepcion'), {
            'proveedor': 'Colanta', 'numero_factura': 'FV-1', 'fecha': timezone.localdate().isoformat()})
        self.assertEqual(Recepcion.objects.count(), 2)

    def test_no_se_acepta_una_fecha_futura(self):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.client.post(reverse('crear_recepcion'), {'proveedor': 'Alpina', 'numero_factura': 'FV-9', 'fecha': manana})
        self.assertEqual(Recepcion.objects.count(), 0)

    def test_las_lineas_nuevas_quedan_pendientes(self):
        # 24C
        recepcion = self.crear()
        self.agregar(recepcion, self.jabon, '12')
        linea = recepcion.lineas.get()
        self.assertFalse(linea.ingresada)
        self.assertEqual(linea.cantidad, Decimal('12'))
        self.jabon.refresh_from_db()
        self.assertEqual(self.jabon.stock, Decimal('10'))          # agregar a la factura no toca el inventario

    def test_un_producto_no_se_repite_en_la_misma_factura(self):
        recepcion = self.crear()
        self.agregar(recepcion, self.jabon, '12')
        self.agregar(recepcion, self.jabon, '5')
        self.assertEqual(recepcion.lineas.count(), 1)

    def test_cantidades_invalidas_se_rechazan(self):
        recepcion = self.crear()
        for cantidad in ('0', '-3', 'abc', '1.5'):               # 1.5 und no es válido en un producto por unidad
            self.agregar(recepcion, self.jabon, cantidad)
        self.assertEqual(recepcion.lineas.count(), 0)

    def test_ingresar_una_linea_suma_al_inventario_y_la_marca(self):
        # 24D
        recepcion = self.crear()
        self.agregar(recepcion, self.jabon, '12')
        linea = recepcion.lineas.get()
        self.ingresar(linea)
        self.jabon.refresh_from_db()
        linea.refresh_from_db()
        self.assertEqual(self.jabon.stock, Decimal('22'))
        self.assertTrue(linea.ingresada)
        self.assertEqual(linea.ingresada_por, self.vendedor)
        self.assertIsNotNone(linea.ingresada_en)

    def test_una_linea_ya_ingresada_no_se_puede_ingresar_otra_vez(self):
        # 24E: el problema original, ingresar dos veces lo mismo
        recepcion = self.crear()
        self.agregar(recepcion, self.jabon, '12')
        linea = recepcion.lineas.get()
        self.ingresar(linea)
        self.ingresar(linea)
        self.jabon.refresh_from_db()
        self.assertEqual(self.jabon.stock, Decimal('22'))          # 10 + 12, no 10 + 24

    def test_el_progreso_y_la_recepcion_completa(self):
        # 24F y 24G
        recepcion = self.crear()
        self.agregar(recepcion, self.jabon, '12')
        self.agregar(recepcion, self.cloro, '4')
        self.ingresar(recepcion.lineas.get(producto=self.jabon))
        respuesta = self.client.get(reverse('detalle_recepcion', args=[recepcion.id]))
        self.assertEqual((respuesta.context['ingresadas'], respuesta.context['total']), (1, 2))
        self.assertFalse(respuesta.context['completa'])
        self.ingresar(recepcion.lineas.get(producto=self.cloro))
        respuesta = self.client.get(reverse('detalle_recepcion', args=[recepcion.id]))
        self.assertTrue(respuesta.context['completa'])
        self.assertTrue(recepcion.esta_completa())

    def test_se_puede_quitar_una_linea_pendiente_pero_no_una_ingresada(self):
        recepcion = self.crear()
        self.agregar(recepcion, self.jabon, '12')
        self.agregar(recepcion, self.cloro, '4')
        pendiente = recepcion.lineas.get(producto=self.cloro)
        ingresada = recepcion.lineas.get(producto=self.jabon)
        self.ingresar(ingresada)
        self.client.post(reverse('quitar_linea_recepcion', args=[recepcion.id, pendiente.id]))
        self.client.post(reverse('quitar_linea_recepcion', args=[recepcion.id, ingresada.id]))
        self.assertEqual(list(recepcion.lineas.values_list('producto__nombre', flat=True)), ['Jabón'])

    def test_sin_iniciar_sesion_no_se_puede_usar(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('lista_recepciones')).status_code, 302)