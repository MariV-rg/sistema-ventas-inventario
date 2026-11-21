from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import Perfil, Rol

INPUT_CLASSES = 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400'


class RegistroUsuarioForm(forms.Form):
    '''
    Formulario para que el administrador registre un usuario nuevo con sus roles (HU2 + HU3).

    HU29: el administrador principal (el superusuario) puede asignar cualquier rol. Un
    administrador común solo puede crear vendedores: el rol Administrador ni siquiera se le
    ofrece, y si alguien lo manda a la fuerza, el formulario lo rechaza.
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
        error_messages={'invalid_choice': 'No tienes permiso para asignar ese rol.'},
    )

    def __init__(self, *args, quien_registra=None, **kwargs):
        super().__init__(*args, **kwargs)
        # 29B y 29C: los roles que se pueden asignar dependen de quién registra.
        # Si no se sabe quién es, se usa lo más restrictivo (solo Vendedor).
        if quien_registra is None or not quien_registra.is_superuser:
            self.fields['roles'].queryset = Rol.objects.filter(nombre=Rol.VENDEDOR)

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


class ConfiguracionInicialForm(forms.Form):
    '''
    HU29 (29F): formulario de la primera vez que se usa el sistema, cuando todavía no existe
    ningún usuario. Crea al administrador principal desde la aplicación, sin usar la terminal.
    '''
    username = forms.CharField(
        label='Usuario', max_length=150,
        widget=forms.TextInput(attrs={'class': INPUT_CLASSES, 'autofocus': True})
    )
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': INPUT_CLASSES})
    )
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASSES})
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASSES})
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Ya existe un usuario con ese nombre.')
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2:
            if password1 != password2:
                self.add_error('password2', 'Las contraseñas no coinciden.')
            else:
                # las reglas de seguridad de Django (largo mínimo, no solo números, etc.)
                usuario = User(username=cleaned.get('username', ''), email=cleaned.get('email', ''))
                try:
                    validate_password(password1, user=usuario)
                except forms.ValidationError as errores:
                    self.add_error('password1', errores)
        return cleaned