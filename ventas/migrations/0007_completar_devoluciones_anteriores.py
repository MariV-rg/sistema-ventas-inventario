from django.db import migrations


def completar_devoluciones_anteriores(apps, schema_editor):
    """
    Las devoluciones que ya existían se hicieron antes de tener motivo, destino y resolución.
    Se les asigna lo que el sistema hacía entonces, para que los cierres de caja anteriores
    no cambien:
      - eran reembolsos por el valor completo,
      - la unidad volvía al inventario,
      - el efectivo solo salía de la caja si la venta se había pagado en efectivo.
    """
    Devolucion = apps.get_model('ventas', 'Devolucion')
    for dev in Devolucion.objects.select_related('detalle__venta'):
        era_efectivo = dev.detalle.venta.metodo_pago == 'EFECTIVO'
        dev.reembolso = dev.valor
        dev.forma_reembolso = 'EFECTIVO' if era_efectivo else 'TRANSFERENCIA'
        dev.detalle_motivo = 'Devolución registrada antes de que existiera el motivo.'
        dev.save(update_fields=['reembolso', 'forma_reembolso', 'detalle_motivo'])


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0006_devolucion_motivo_resolucion'),
    ]

    operations = [
        migrations.RunPython(completar_devoluciones_anteriores, migrations.RunPython.noop),
    ]