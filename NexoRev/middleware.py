from django.shortcuts import redirect
from django.http import JsonResponse


class RoleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            return self.get_response(request)

        role = request.session.get('current_user_role')
        if not request.session.get('current_user'):
            if request.path.startswith('/principal'):
                if request.path.startswith('/principal/api/'):
                    return JsonResponse(
                        {'success': False, 'error': 'Tu sesión expiró. Inicia sesión nuevamente.'},
                        status=401,
                    )
                return redirect('login')
            return self.get_response(request)

        if request.path.startswith('/principal/doctor/') and role != 'doctor':
            return redirect('principal')
        if request.path.startswith('/principal/paciente/') and role != 'paciente':
            return redirect('principal')

        return self.get_response(request)
