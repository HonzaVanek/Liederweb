from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from .forms import VlastniLoginForm, RegistraceForm
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage

def home(request):
    return render(request, 'core/home.html')

class VlastniLoginView(LoginView):
    template_name = 'core/login.html'
    form_class = VlastniLoginForm


def registrace(request):
    if request.method == 'POST':
        form = RegistraceForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # ----- DEV REŽIM -----
            if settings.APP_ENV == "dev":
                user.is_active = True
                user.save()
                login(request, user)
                return redirect('home')

            # ----- PROD REŽIM ----- (zatím nelze)
            user.is_active = False
            user.save()

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            current_site = get_current_site(request)
            activation_link = f"http://{current_site.domain}{reverse('activate', args=[uidb64, token])}"

            subject = 'Aktivuj si účet'
            message = render_to_string(
                'registration/activation_email.txt',
                {'user': user, 'activation_link': activation_link}
            )

            email = EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL, to=[user.email])
            email.send(fail_silently=False)

            return render(request, 'core/registration_complete.html', {'form': form})

    else:
        form = RegistraceForm()

    return render(request, 'core/registrace.html', {'form': form})

def activate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Váš účet byl aktivován, nyní se můžete přihlásit.')
        return redirect('login')
    else:
        return render(request, 'core/activation_invalid.html')