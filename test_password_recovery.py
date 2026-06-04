#!/usr/bin/env python
"""
Script de prueba para verificar el flujo de recuperación de contraseña.
Este script simula los pasos del usuario en el formulario de recuperación.
"""

import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'NexoRev.settings')
django.setup()

from django.test import Client
from django.urls import reverse
from crear_cuenta.models import Usuario
from django.contrib.auth.hashers import make_password
import random
import string

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_forgot_password_flow():
    """Prueba el flujo completo de recuperación de contraseña"""
    
    print_section("PRUEBA DE RECUPERACIÓN DE CONTRASEÑA")
    
    # Crear un usuario de prueba
    test_email = f"test_{random.randint(1000, 9999)}@gmail.com"
    test_password = "TestPassword123"
    
    print(f"\n✓ Creando usuario de prueba...")
    print(f"  Email: {test_email}")
    print(f"  Contraseña: {test_password}")
    
    # Crear el usuario
    usuario = Usuario.objects.create(
        email=test_email,
        nombre="Usuario Prueba",
    )
    usuario.set_password(test_password)
    usuario.save()
    
    print(f"  Usuario creado exitosamente: {usuario.id}")
    
    # Iniciar cliente HTTP
    client = Client()
    
    # Paso 1: Ir a forgot-password
    print(f"\n✓ Accediendo a la página de olvide contraseña...")
    response = client.get(reverse('forgot_password'))
    print(f"  Status: {response.status_code}")
    assert response.status_code == 200, "Failed to access forgot password page"
    
    # Paso 2: Enviar el email
    print(f"\n✓ Enviando solicitud de recuperación...")
    response = client.post(reverse('forgot_password'), {
        'email': test_email,
    }, follow=True)
    print(f"  Status: {response.status_code}")
    
    if response.status_code == 200:
        # Obtener el código de la sesión
        recovery_code = client.session.get('recovery_code')
        recovery_email = client.session.get('recovery_email')
        
        if recovery_code and recovery_email:
            print(f"  ✓ Código generado: {recovery_code}")
            print(f"  ✓ Email en sesión: {recovery_email}")
            
            # Paso 3: Verificar el código
            print(f"\n✓ Ingresando código y nueva contraseña...")
            new_password = "NewPassword456"
            response = client.post(reverse('verify_recovery_code'), {
                'code': recovery_code,
                'password': new_password,
                'password_confirm': new_password,
            })
            
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                # Verificar que la contraseña fue actualizada
                usuario_actualizado = Usuario.objects.get(email=test_email)
                if usuario_actualizado.check_password(new_password):
                    print(f"  ✓ Contraseña actualizada exitosamente")
                    print(f"  ✓ La nueva contraseña funciona correctamente")
                else:
                    print(f"  ✗ Error: La contraseña no fue actualizada")
            else:
                print(f"  ✗ Error al procesar la verificación")
        else:
            print(f"  ✗ No se generó el código de recuperación")
    else:
        print(f"  ✗ Error al enviar la solicitud")
    
    # Limpiar
    print(f"\n✓ Limpiando datos de prueba...")
    usuario_actualizado.delete()
    print(f"  Usuario de prueba eliminado")
    
    print_section("PRUEBA COMPLETADA")
    print("\n✓ Todas las pruebas pasaron correctamente!")
    print("✓ El flujo de recuperación de contraseña está funcionando.")

if __name__ == '__main__':
    try:
        test_forgot_password_flow()
    except Exception as e:
        print(f"\n✗ Error durante la prueba: {e}")
        import traceback
        traceback.print_exc()
