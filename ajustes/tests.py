from django.test import RequestFactory, SimpleTestCase

from .views import ajustes_view


class AjustesViewTests(SimpleTestCase):
    def test_renders_current_user_for_preferences(self):
        request = RequestFactory().get('/ajustes/')
        request.session = {'current_user': 'Usuario@Ejemplo.com'}

        response = ajustes_view(request)

        self.assertContains(response, 'data-current-user="usuario@ejemplo.com"')
