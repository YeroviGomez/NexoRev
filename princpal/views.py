from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

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

    return render(request, 'principal.html', {
        'show_tutorial': show_tutorial,
        'usuario': usuario,
        'current_user_email': current_user_email,
        'dark_mode': usuario.modo_oscuro if usuario else False,
    })


@csrf_exempt
@require_http_methods(["POST"])
def update_profile(request):
    """Actualizar datos del perfil del usuario"""
    try:
        data = json.loads(request.body)
        current_user_email = request.session.get('current_user', '')
        
        if not current_user_email:
            return JsonResponse({'success': False, 'error': 'Usuario no autenticado'}, status=401)
        
        usuario = Usuario.objects.get(email=current_user_email)
        
        # Actualizar campos
        if 'nombre' in data and data['nombre']:
            usuario.nombre = data['nombre']
        
        if 'telefono' in data:
            usuario.telefono = data['telefono']
        
        if 'edad' in data:
            try:
                usuario.edad = int(data['edad']) if data['edad'] else None
            except (ValueError, TypeError):
                usuario.edad = None
        
        # Si el email cambió, verificar que sea único
        new_email = None
        if 'email' in data and data['email'] and data['email'] != current_user_email:
            if Usuario.objects.filter(email=data['email']).exclude(id=usuario.id).exists():
                return JsonResponse({'success': False, 'error': 'El correo ya está registrado'}, status=400)
            new_email = data['email']
            usuario.email = new_email
        
        usuario.save()
        
        # Actualizar la sesión con el nuevo email si cambió
        if new_email:
            request.session['current_user'] = new_email
        
        return JsonResponse({'success': True, 'message': 'Perfil actualizado correctamente'})
    
    except Usuario.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos inválidos'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def change_password(request):
    """Cambiar contraseña del usuario"""
    try:
        data = json.loads(request.body)
        current_user_email = request.session.get('current_user', '')
        
        if not current_user_email:
            return JsonResponse({'success': False, 'error': 'Usuario no autenticado'}, status=401)
        
        usuario = Usuario.objects.get(email=current_user_email)
        
        current_password = data.get('currentPassword', '').strip()
        new_password = data.get('newPassword', '').strip()
        confirm_password = data.get('confirmPassword', '').strip()
        
        # Validaciones
        if not all([current_password, new_password, confirm_password]):
            return JsonResponse({'success': False, 'error': 'Por favor completa todos los campos de contraseña'}, status=400)
        
        if new_password != confirm_password:
            return JsonResponse({'success': False, 'error': 'Las nuevas contraseñas no coinciden'}, status=400)
        
        if len(new_password) < 6:
            return JsonResponse({'success': False, 'error': 'La nueva contraseña debe tener al menos 6 caracteres'}, status=400)
        
        if not usuario.check_password(current_password):
            return JsonResponse({'success': False, 'error': 'La contraseña actual es incorrecta'}, status=400)
        
        if current_password == new_password:
            return JsonResponse({'success': False, 'error': 'La nueva contraseña no puede ser igual a la actual'}, status=400)
        
        usuario.set_password(new_password)
        usuario.save()
        
        return JsonResponse({'success': True, 'message': 'Contraseña cambiada correctamente'})
    
    except Usuario.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos inválidos'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def upload_profile_photo(request):
    """Cambiar foto de perfil del usuario"""
    try:
        current_user_email = request.session.get('current_user', '')
        
        if not current_user_email:
            return JsonResponse({'success': False, 'error': 'Usuario no autenticado'}, status=401)
        
        if 'foto' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No se envió archivo'}, status=400)
        
        usuario = Usuario.objects.get(email=current_user_email)
        archivo_foto = request.FILES['foto']
        
        # Validar tipo de archivo
        tipos_permitidos = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if archivo_foto.content_type not in tipos_permitidos:
            return JsonResponse({'success': False, 'error': 'Solo se permiten imágenes (JPG, PNG, GIF, WebP)'}, status=400)
        
        # Validar tamaño (máximo 5MB)
        if archivo_foto.size > 5 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'La imagen no debe superar 5MB'}, status=400)
        
        # Eliminar foto anterior si existe
        if usuario.foto:
            try:
                usuario.foto.delete()
            except:
                pass
        
        # Asignar y guardar la nueva foto
        usuario.foto = archivo_foto
        usuario.save()
        
        # Verificar que se guardó
        if usuario.foto:
            return JsonResponse({
                'success': True, 
                'message': 'Foto actualizada correctamente',
                'foto_url': usuario.foto.url if usuario.foto else ''
            })
        else:
            return JsonResponse({'success': False, 'error': 'No se pudo guardar la imagen'}, status=500)
    
    except Usuario.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Error: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def toggle_dark_mode(request):
    """Cambiar preferencia de modo oscuro"""
    try:
        data = json.loads(request.body)
        current_user_email = request.session.get('current_user', '')
        
        if not current_user_email:
            return JsonResponse({'success': False, 'error': 'Usuario no autenticado'}, status=401)
        
        usuario = Usuario.objects.get(email=current_user_email)
        
        # Toggle del modo oscuro
        modo_oscuro = data.get('modo_oscuro', False)
        usuario.modo_oscuro = modo_oscuro
        usuario.save()
        
        return JsonResponse({'success': True, 'modo_oscuro': usuario.modo_oscuro})
    
    except Usuario.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos inválidos'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
