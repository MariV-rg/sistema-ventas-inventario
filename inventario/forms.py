from django import forms
from .models import Producto


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            'nombre', 'categoria', 'tipo_venta',
            'precio', 'stock', 'stock_minimo',
            'unidades_por_paquete', 'precio_paquete',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400'
            }),
            'categoria': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400'
            }),
            'tipo_venta': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400'
            }),
            'precio': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2', 'step': '0.01'
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2', 'step': '0.001'
            }),
            'stock_minimo': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2', 'step': '0.001'
            }),
            'unidades_por_paquete': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2'
            }),
            'precio_paquete': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2', 'step': '0.01'
            }),
        }

    def clean(self):
        cleaned = super().clean()
        tipo_venta = cleaned.get('tipo_venta')
        precio = cleaned.get('precio')

        # 5D/5E/5F: Unidad y Peso necesitan precio (5G: Libre no lo exige)
        if tipo_venta in (Producto.UNIDAD, Producto.PESO) and precio is None:
            self.add_error('precio', 'Este producto necesita un precio (por unidad o por kilo).')

        # 5H: el paquete solo aplica a productos "Por unidad"
        unidades_paquete = cleaned.get('unidades_por_paquete')
        precio_paquete = cleaned.get('precio_paquete')
        paquete_definido = unidades_paquete is not None or precio_paquete is not None

        if paquete_definido and tipo_venta != Producto.UNIDAD:
            self.add_error('unidades_por_paquete', 'El precio por paquete solo aplica a productos "Por unidad".')
        if paquete_definido and (unidades_paquete is None or precio_paquete is None):
            self.add_error('precio_paquete', 'Si define paquete, debe llenar tanto las unidades como el precio del paquete.')

        return cleaned