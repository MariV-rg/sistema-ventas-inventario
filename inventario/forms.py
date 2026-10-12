from django import forms
from .models import Producto

INPUT = 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400'


class ProductoForm(forms.ModelForm):
    '''
    Formulario de producto. Se usa en HU5 (registrar) y se reutiliza en HU6 (editar)
    pasándole instance=producto.
    '''

    class Meta:
        model = Producto
        fields = ['nombre', 'categoria', 'precio', 'unidad_base', 'stock_minimo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': INPUT}),
            'categoria': forms.Select(attrs={'class': INPUT + ' invalid:text-gray-400 [&>option]:text-gray-900'}),
            'precio': forms.NumberInput(attrs={'class': INPUT, 'step': '0.01', 'min': '0'}),
            'unidad_base': forms.Select(attrs={'class': INPUT}),
            'stock_minimo': forms.NumberInput(attrs={'class': INPUT, 'step': '0.001', 'min': '0'}),
        }
        labels = {
            'nombre': 'Nombre',
            'categoria': 'Categoría',
            'precio': 'Precio',
            'unidad_base': 'Unidad base de inventario',
            'stock_minimo': 'Stock mínimo (alerta)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 5F: el stock mínimo es opcional; si se deja vacío queda en 0
        self.fields['stock_minimo'].required = False
        self.fields['categoria'].empty_label = 'Seleccione la categoría...'
        self.fields['unidad_base'].choices = [('', 'Seleccione la unidad...')] + list(Producto.UNIDAD_BASE_CHOICES)

    def clean_stock_minimo(self):
        return self.cleaned_data.get('stock_minimo') or 0

    # 5C: no repetir productos (sin importar mayúsculas). Al editar (HU6) se ignora a sí mismo.
    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        repetidos = Producto.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise forms.ValidationError('Ya existe un producto con ese nombre.')
        return nombre