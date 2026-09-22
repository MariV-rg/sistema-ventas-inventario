from django import forms
from django.contrib.auth.models import User
from .models import Perfil, Rol

INPUT_CLASSES = 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400'


class RegistroUsuarioForm(forms.Form):
    '''
    Formulario para que el administrador registre un usuario nuevo con sus roles (HU2 + HU3).
    '''
    username = forms.CharField(
        label='Usuario', max_length=150,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES})
    )
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASSES + ' pr-10'})
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASSES + ' pr-10'})
    )
    # HU3: ahora se pueden marcar varios roles a la vez (checkboxes en vez de un solo select)
    roles = forms.ModelMultipleChoiceField(
        label='Roles',
        queryset=Rol.objects.all(),
        widget=forms.CheckboxSelectMultiple,
    )

    # 2C: evitar usuarios duplicados
    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Ya existe un usuario con ese nombre.')
        return username

    # Confirmar que las dos contraseñas coincidan
    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        return cleaned