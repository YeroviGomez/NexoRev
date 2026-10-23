from django.shortcuts import redirect
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


class SessionRevocationCsrfMiddleware(CsrfViewMiddleware):
    def _origin_verified(self, request):
        path = request.path_info
        is_revocation_path = (
            path.startswith('/sesion-no-reconocida/')
            or path.startswith('/login/sesion-no-reconocida/')
        )
        if (
            request.method == 'POST'
            and is_revocation_path
            and request.META.get('HTTP_ORIGIN') == 'null'
        ):
            return True
        return super()._origin_verified(request)


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
