from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Perfil, Rol
from inventario.models import Categoria, Producto

from .models import Caja, DetalleVenta, Devolucion, RegistroBaja, Venta


class EliminarHistorialTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('principal', password='Tienda-Segura-2026')
        self.vendedor = User.objects.create_user('vend', password='Tienda-Segura-2026')
        Perfil.objects.create(usuario=self.vendedor).roles.set([Rol.objects.get(nombre=Rol.VENDEDOR)])

        # las categorías iniciales ya las crea una migración, así que se usa la que existe
        categoria, _ = Categoria.objects.get_or_create(nombre='Aseo')
        self.producto = Producto.objects.create(
            categoria=categoria, nombre='Jabón', precio=Decimal('2000'), stock=Decimal('10'))

        hoy = timezone.localdate()
        self.mes_actual = hoy.replace(day=1)
        self.mes_pasado = (self.mes_actual - timedelta(days=1)).replace(day=1)
        self.client.force_login(self.admin)

    def crear_venta(self, dia, caja=None):
        """Crea una venta con una línea y la deja con la fecha pedida (para poder ponerla en un mes viejo)."""
        venta = Venta.objects.create(vendedor=self.vendedor, metodo_pago=Venta.EFECTIVO,
                                     total=Decimal('4000'), caja=caja)
        detalle = DetalleVenta.objects.create(
            venta=venta, producto=self.producto, cantidad=Decimal('2'),
            precio_unitario=Decimal('2000'), subtotal=Decimal('4000'))
        zona = timezone.get_current_timezone()
        Venta.objects.filter(id=venta.id).update(fecha=datetime.combine(dia, time(12, 0), tzinfo=zona))
        return venta, detalle

    def caja_cerrada(self):
        return Caja.objects.create(
            vendedor=self.vendedor, monto_inicial=Decimal('50000'), abierta=False,
            monto_esperado=Decimal('54000'), monto_final=Decimal('54000'), diferencia=Decimal('0'))

    def url_confirmar(self, mes):
        return reverse('confirmar_eliminar_historial', args=[mes.year, mes.month])

    def test_la_lista_muestra_los_meses_y_marca_el_actual_como_en_uso(self):
        self.crear_venta(self.mes_pasado.replace(day=15))
        self.crear_venta(self.mes_actual)
        respuesta = self.client.get(reverse('eliminar_historial'))
        self.assertEqual(respuesta.status_code, 200)
        meses = {m['inicio']: m for m in respuesta.context['meses']}
        self.assertIsNone(meses[self.mes_pasado]['bloqueo'])
        self.assertIsNotNone(meses[self.mes_actual]['bloqueo'])           # 21D

    def test_la_confirmacion_muestra_lo_que_se_va_a_eliminar(self):
        self.crear_venta(self.mes_pasado.replace(day=15))
        respuesta = self.client.get(self.url_confirmar(self.mes_pasado))   # 21A
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['resumen']['ventas'], 1)
        self.assertEqual(respuesta.context['resumen']['lineas'], 1)
        self.assertTrue(Venta.objects.exists())                           # ver la pantalla no borra nada

    def test_confirmar_elimina_ventas_lineas_y_devoluciones_pero_conserva_cajas_e_inventario(self):
        caja = self.caja_cerrada()
        venta, detalle = self.crear_venta(self.mes_pasado.replace(day=15), caja=caja)
        Devolucion.objects.create(
            detalle=detalle, cantidad=Decimal('1'), valor=Decimal('2000'), vendedor=self.vendedor,
            caja=caja, reembolso=Decimal('2000'), forma_reembolso=Devolucion.FORMA_EFECTIVO)
        stock_antes = Producto.objects.get(id=self.producto.id).stock

        respuesta = self.client.post(self.url_confirmar(self.mes_pasado), {'confirmacion': 'si'})

        self.assertRedirects(respuesta, reverse('eliminar_historial'))
        self.assertFalse(Venta.objects.exists())                          # 21B
        self.assertFalse(DetalleVenta.objects.exists())
        self.assertFalse(Devolucion.objects.exists())
        self.assertTrue(Caja.objects.filter(id=caja.id).exists())         # los cierres de caja se conservan
        self.assertEqual(Producto.objects.get(id=self.producto.id).stock, stock_antes)

    def test_solo_se_elimina_el_mes_elegido(self):
        otro_mes = (self.mes_pasado - timedelta(days=1)).replace(day=1)
        self.crear_venta(self.mes_pasado.replace(day=15))
        venta_otro, _ = self.crear_venta(otro_mes.replace(day=15))
        self.client.post(self.url_confirmar(self.mes_pasado), {'confirmacion': 'si'})
        self.assertEqual(list(Venta.objects.values_list('id', flat=True)), [venta_otro.id])

    def test_decir_que_no_no_elimina_nada(self):
        # 21C
        self.crear_venta(self.mes_pasado.replace(day=15))
        self.client.post(self.url_confirmar(self.mes_pasado), {'confirmacion': 'no'})
        self.assertEqual(Venta.objects.count(), 1)

    def test_no_se_puede_eliminar_el_mes_actual(self):
        # 21D
        self.crear_venta(self.mes_actual)
        respuesta = self.client.get(self.url_confirmar(self.mes_actual))
        self.assertRedirects(respuesta, reverse('eliminar_historial'))
        self.client.post(self.url_confirmar(self.mes_actual), {'confirmacion': 'si'})
        self.assertEqual(Venta.objects.count(), 1)

    def test_no_se_puede_eliminar_un_mes_con_ventas_de_una_caja_abierta(self):
        caja_abierta = Caja.objects.create(vendedor=self.vendedor, monto_inicial=Decimal('1000'))
        self.crear_venta(self.mes_pasado.replace(day=15), caja=caja_abierta)
        self.client.post(self.url_confirmar(self.mes_pasado), {'confirmacion': 'si'})
        self.assertEqual(Venta.objects.count(), 1)

    def test_un_vendedor_no_puede_usar_esta_funcion(self):
        self.crear_venta(self.mes_pasado.replace(day=15))
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(reverse('eliminar_historial')).status_code, 302)
        self.client.post(self.url_confirmar(self.mes_pasado), {'confirmacion': 'si'})
        self.assertEqual(Venta.objects.count(), 1)


class BajasTests(TestCase):
    def setUp(self):
        self.vendedor = User.objects.create_user('vend', password='Tienda-Segura-2026')
        Perfil.objects.create(usuario=self.vendedor).roles.set([Rol.objects.get(nombre=Rol.VENDEDOR)])
        self.client.force_login(self.vendedor)           # lo puede hacer cualquier empleado

        categoria, _ = Categoria.objects.get_or_create(nombre='Aseo')
        self.yogur = Producto.objects.create(categoria=categoria, nombre='Yogur', precio=Decimal('3000'),
                                             stock=Decimal('10'), recibe_cambio=True)
        self.jabon = Producto.objects.create(categoria=categoria, nombre='Jabón', precio=Decimal('2000'),
                                             stock=Decimal('10'), recibe_cambio=False)

    def registrar(self, producto, cantidad='2', motivo='VENCIDO', detalle=''):
        return self.client.post(reverse('registrar_baja'), {
            'producto': producto.id, 'cantidad': cantidad, 'motivo': motivo, 'detalle_motivo': detalle})

    def devolucion(self, destino):
        venta = Venta.objects.create(vendedor=self.vendedor, metodo_pago=Venta.EFECTIVO, total=Decimal('3000'))
        detalle = DetalleVenta.objects.create(venta=venta, producto=self.yogur, cantidad=Decimal('1'),
                                              precio_unitario=Decimal('3000'), subtotal=Decimal('3000'))
        return Devolucion.objects.create(
            detalle=detalle, cantidad=Decimal('1'), valor=Decimal('3000'), vendedor=self.vendedor,
            motivo=Devolucion.MOTIVO_VENCIDO, destino=destino, reembolso=Decimal('3000'),
            forma_reembolso=Devolucion.FORMA_EFECTIVO)

    def test_registrar_una_baja_la_descuenta_del_inventario_y_queda_pendiente_si_recibe_cambio(self):
        # 25B y 25C
        self.registrar(self.yogur, '3')
        self.yogur.refresh_from_db()
        self.assertEqual(self.yogur.stock, Decimal('7'))
        baja = RegistroBaja.objects.get()
        self.assertEqual(baja.estado, RegistroBaja.ESTADO_PENDIENTE)
        self.assertEqual(baja.origen, RegistroBaja.ORIGEN_INVENTARIO)
        self.assertEqual(baja.registrada_por, self.vendedor)

    def test_un_producto_que_no_recibe_cambio_queda_como_perdida(self):
        # 25E
        self.registrar(self.jabon, '2')
        self.assertEqual(RegistroBaja.objects.get().estado, RegistroBaja.ESTADO_PERDIDA)

    def test_no_se_da_de_baja_mas_de_lo_que_hay_en_el_inventario(self):
        self.registrar(self.yogur, '11')
        self.assertFalse(RegistroBaja.objects.exists())
        self.yogur.refresh_from_db()
        self.assertEqual(self.yogur.stock, Decimal('10'))

    def test_datos_invalidos_no_registran_nada(self):
        self.registrar(self.yogur, '0')
        self.registrar(self.yogur, '1.5')                                  # unidades enteras
        self.registrar(self.yogur, '2', motivo='')
        self.registrar(self.yogur, '2', motivo='OTRO', detalle='')         # "otro" exige explicación
        self.assertFalse(RegistroBaja.objects.exists())

    def test_marcar_como_cambiada(self):
        # 25D
        self.registrar(self.yogur, '3')
        baja = RegistroBaja.objects.get()
        self.client.post(reverse('marcar_baja_cambiada', args=[baja.id]))
        baja.refresh_from_db()
        self.assertEqual(baja.estado, RegistroBaja.ESTADO_CAMBIADO)
        self.assertEqual(baja.cambiada_por, self.vendedor)
        self.assertIsNotNone(baja.cambiada_en)
        self.yogur.refresh_from_db()
        self.assertEqual(self.yogur.stock, Decimal('7'))       # las unidades nuevas entran por una recepción, no aquí

    def test_una_perdida_no_se_puede_marcar_como_cambiada(self):
        self.registrar(self.jabon, '2')
        baja = RegistroBaja.objects.get()
        self.client.post(reverse('marcar_baja_cambiada', args=[baja.id]))
        baja.refresh_from_db()
        self.assertEqual(baja.estado, RegistroBaja.ESTADO_PERDIDA)

    def test_las_devoluciones_que_no_volvieron_al_inventario_aparecen_solas(self):
        # 25A
        self.devolucion(Devolucion.DESTINO_CAMBIO)
        self.devolucion(Devolucion.DESTINO_PERDIDA)
        self.devolucion(Devolucion.DESTINO_STOCK)                           # esta volvió al inventario: no es baja
        self.client.get(reverse('lista_bajas'))
        self.assertEqual(RegistroBaja.objects.count(), 2)
        estados = set(RegistroBaja.objects.values_list('estado', flat=True))
        self.assertEqual(estados, {RegistroBaja.ESTADO_PENDIENTE, RegistroBaja.ESTADO_PERDIDA})
        self.client.get(reverse('lista_bajas'))                             # volver a abrir no duplica nada
        self.assertEqual(RegistroBaja.objects.count(), 2)

    def test_filtrar_por_estado(self):
        # 25F
        self.registrar(self.yogur, '1')
        self.registrar(self.jabon, '1')
        respuesta = self.client.get(reverse('lista_bajas') + '?estado=PERDIDA')
        self.assertEqual([f['baja'].producto.nombre for f in respuesta.context['filas']], ['Jabón'])

    def test_sin_iniciar_sesion_no_se_puede_usar(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('lista_bajas')).status_code, 302)