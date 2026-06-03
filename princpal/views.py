from django.shortcuts import render

from crear_cuenta.models import Usuario


def principal_view(request):
    show_tutorial = request.session.pop('show_tutorial', False)
    current_user_email = request.session.get('current_user', '')
    usuario = None

    if current_user_email:
        try:
            usuario = Usuario.objects.get(email=current_user_email)
        except Usuario.DoesNotExist:
            usuario = None

    videos = [
        {
            'title': 'Ejercicios para dolor de rodilla',
            'description': 'Rutina básica para fortalecer la rodilla y reducir el dolor',
            'duration': '10:45',
            'difficulty': 'easy',
            'level': 'Principiante',
            'category': 'Rodilla',
        },
        {
            'title': 'Rehabilitación de hombro',
            'description': 'Ejercicios de movilidad para recuperar el rango de movimiento del hombro',
            'duration': '15:30',
            'difficulty': 'medium',
            'level': 'Intermedio',
            'category': 'Hombro',
        },
        {
            'title': 'Fortalecimiento de espalda baja',
            'description': 'Rutina completa para fortalecer la zona lumbar y prevenir lesiones',
            'duration': '20:00',
            'difficulty': 'medium',
            'level': 'Intermedio',
            'category': 'Espalda',
        },
        {
            'title': 'Estiramiento de cuello y cervicales',
            'description': 'Ejercicios suaves para aliviar la tensión en cuello y cervicales',
            'duration': '8:15',
            'difficulty': 'easy',
            'level': 'Principiante',
            'category': 'Cuello',
        },
        {
            'title': 'Recuperación de tobillo',
            'description': 'Ejercicios progresivos para rehabilitar esguinces de tobillo',
            'duration': '12:30',
            'difficulty': 'easy',
            'level': 'Principiante',
            'category': 'Tobillo',
        },
        {
            'title': 'Movilidad de cadera',
            'description': 'Rutina avanzada para mejorar la flexibilidad y fuerza de la cadera',
            'duration': '18:45',
            'difficulty': 'hard',
            'level': 'Avanzado',
            'category': 'Cadera',
        },
    ]
    categories = ['Todas', 'Rodilla', 'Hombro', 'Espalda', 'Cuello', 'Tobillo', 'Cadera']

    return render(request, 'principal.html', {
        'show_tutorial': show_tutorial,
        'usuario': usuario,
        'current_user_email': current_user_email,
        'videos': videos,
        'categories': categories,
    })
