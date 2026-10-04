from django.shortcuts import render


def ajustes_view(request):
    current_user_email = (request.session.get('current_user') or '').strip().lower()
    return render(request, 'ajustes.html', {'current_user_email': current_user_email})
