import json

from django.test import Client, TestCase
from django.urls import reverse

from .models import SecurityQuestion, Usuario


class SecurityQuestionSettingsTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create(
            email='security-settings@example.com',
            nombre='Usuario de prueba',
        )
        self.client = Client()
        session = self.client.session
        session['current_user'] = self.user.email
        session.save()
        self.url = reverse('update_security_questions')

    def post_questions(self, questions):
        return self.client.post(
            self.url,
            data=json.dumps({'questions': questions}),
            content_type='application/json',
        )

    def test_saves_two_predefined_questions_with_hashed_answers(self):
        response = self.post_questions([
            {'type': 'predefined', 'key': 'first_pet', 'answer': '  Fido  '},
            {'type': 'predefined', 'key': 'birth_city', 'answer': 'San Salvador'},
        ])

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        questions = list(SecurityQuestion.objects.filter(user=self.user))
        self.assertEqual(len(questions), 2)
        self.assertNotEqual(questions[0].answer_hash, 'Fido')
        self.assertTrue(questions[0].check_answer('fido'))
        self.assertNotIn('answer_hash', response.json())
        self.assertNotContains(self.client.get(reverse('principal')), 'Fido')

    def test_accepts_custom_question_and_rejects_short_blank_and_duplicate_questions(self):
        custom_questions = [
            {'type': 'custom', 'question': '¿Cuál fue tu primer viaje?', 'answer': 'Costa Rica'},
            {'type': 'predefined', 'key': 'first_job', 'answer': 'Docente'},
        ]
        saved = self.post_questions(custom_questions)
        short = self.post_questions([
            {'type': 'custom', 'question': '¿Tu edad?', 'answer': '30'},
            {'type': 'predefined', 'key': 'first_job', 'answer': 'Docente'},
        ])
        duplicate = self.post_questions([
            {'type': 'custom', 'question': '¿Cuál fue tu primer viaje?', 'answer': 'Costa Rica'},
            {'type': 'custom', 'question': ' ¿CUÁL fue tu primer viaje? ', 'answer': 'Costa Rica'},
        ])
        blank_answer = self.post_questions([
            {'type': 'predefined', 'key': 'first_pet', 'answer': ' '},
            {'type': 'predefined', 'key': 'first_job', 'answer': 'Docente'},
        ])
        fewer_than_two = self.post_questions([
            {'type': 'predefined', 'key': 'first_pet', 'answer': 'Fido'},
        ])

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(short.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(blank_answer.status_code, 400)
        self.assertEqual(fewer_than_two.status_code, 400)
        self.assertEqual(SecurityQuestion.objects.filter(user=self.user).count(), 2)

    def test_updates_and_deletes_questions_without_allowing_fewer_than_two(self):
        self.post_questions([
            {'type': 'predefined', 'key': 'first_pet', 'answer': 'Fido'},
            {'type': 'predefined', 'key': 'birth_city', 'answer': 'San Salvador'},
            {'type': 'predefined', 'key': 'first_job', 'answer': 'Docente'},
        ])
        updated = self.post_questions([
            {'type': 'predefined', 'key': 'favorite_food', 'answer': 'Pupusas'},
            {'type': 'custom', 'question': '¿Cuál era tu primer deporte?', 'answer': 'Natación'},
        ])

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            set(SecurityQuestion.objects.filter(user=self.user).values_list('question', flat=True)),
            {'¿Cuál es tu comida favorita?', '¿Cuál era tu primer deporte?'},
        )

    def test_security_question_configuration_requires_the_authenticated_owner(self):
        self.client.session.flush()
        response = self.post_questions([
            {'type': 'predefined', 'key': 'first_pet', 'answer': 'Fido'},
            {'type': 'predefined', 'key': 'birth_city', 'answer': 'San Salvador'},
        ])

        self.assertEqual(response.status_code, 401)
        self.assertFalse(SecurityQuestion.objects.exists())
