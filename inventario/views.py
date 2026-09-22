from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from accounts.views import es_administrador


@login_required
def home(request):
    return render(request, 'home.html', {'es_admin': es_administrador(request.user)})