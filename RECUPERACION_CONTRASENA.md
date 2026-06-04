# Recuperación de Contraseña - Documentación

## 📋 Descripción General

Se ha implementado un flujo completo y seguro de recuperación de contraseña sin modificar la base de datos. El sistema utiliza sesiones y códigos temporales de 6 dígitos.

## 🔄 Flujo del Usuario

### 1. **Página de Login**
- El usuario hace clic en "¿Olvidaste tu contraseña?"
- Se redirige a `/login/forgot-password/`

### 2. **Formulario de Correo** (`forgot_password.html`)
```
┌─────────────────────────────┐
│  RECUPERAR CONTRASEÑA       │
├─────────────────────────────┤
│ Ingresa tu correo           │
│ [correo@ejemplo.com      ]  │
│                             │
│ [ENVIAR CÓDIGO]             │
│ Volver al inicio de sesión  │
└─────────────────────────────┘
```

**Acciones:**
- Valida que el correo sea válido
- Verifica que el usuario existe en el sistema
- Genera un código de 6 dígitos
- Envía el código por email
- Redirige a `/login/verify-recovery-code/`
- **Duración**: El código es válido por 15 minutos

### 3. **Formulario de Recuperación** (`verify_recovery_code.html`)
```
┌──────────────────────────────────┐
│  CAMBIAR CONTRASEÑA              │
├──────────────────────────────────┤
│ Código de Recuperación           │
│ [000000]                         │
│                                  │
│ Nueva Contraseña                 │
│ [••••••••] (mín. 8 caracteres)   │
│                                  │
│ Confirmar Contraseña             │
│ [••••••••]                       │
│                                  │
│ [CAMBIAR CONTRASEÑA]             │
│ Solicitar un nuevo código        │
└──────────────────────────────────┘
```

**Acciones:**
- Valida el código de 6 dígitos
- Verifica que la contraseña tenga al menos 8 caracteres
- Verifica que contenga letras Y números
- Valida que ambas contraseñas coincidan
- Actualiza la contraseña del usuario
- Limpia la sesión
- Muestra mensaje de éxito

### 4. **Confirmación de Éxito**
```
┌──────────────────────────────┐
│  ¡ÉXITO!                     │
├──────────────────────────────┤
│ Tu contraseña ha sido        │
│ actualizada correctamente.   │
│                              │
│ Contraseña actualizada...    │
│                              │
│ [IR AL INICIO DE SESIÓN]     │
└──────────────────────────────┘
```

## 🔐 Características de Seguridad

✅ **Validación de Código:**
- Código de 6 dígitos aleatorios
- Válido por 15 minutos
- Se invalida después de usarse
- Se almacena solo en sesión (no en BD)

✅ **Validación de Contraseña:**
- Mínimo 8 caracteres
- Debe contener letras Y números
- Confirmación de contraseña
- Se usa hashing seguro (Django make_password)

✅ **Seguridad de Email:**
- Valida dominios permitidos
- Verifica que el usuario existe
- No revela si un email está registrado o no

✅ **Validación de Sesión:**
- Timeout de 15 minutos para el código
- Se limpia después de usarse
- Se limpia si hay error

## 📧 Configuración de Email

La aplicación ya tiene configurada la siguiente credencial en `settings.py`:

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'nexorevofi@gmail.com'
EMAIL_HOST_PASSWORD = 'vvfaadaovwkqfydp'
```

**Nota:** Esta es una contraseña de aplicación de Google (App Password), no la contraseña de la cuenta.

## 🗂️ Archivos Modificados

### Backend
- ✅ `login/views.py` - Vistas actualizadas con mejor validación
- ✅ `login/urls.py` - Rutas ya configuradas
- ✅ `login/models.py` - Modelos disponibles (no se usan en BD)

### Frontend
- ✅ `login/templates/login.html` - Botón "¿Olvidaste tu contraseña?"
- ✅ `login/templates/login/forgot_password.html` - Mejorado
- ✅ `login/templates/login/verify_recovery_code.html` - Mejorado

### Estilos
- ✅ `login/static/arte.css` - Estilos para mensajes mejorados

## 🧪 Pruebas

Se incluye un script de prueba: `test_password_recovery.py`

Para ejecutar la prueba:
```bash
python manage.py shell < test_password_recovery.py
```

O desde la shell de Django:
```python
from test_password_recovery import test_forgot_password_flow
test_forgot_password_flow()
```

## 📱 Dominios de Email Permitidos

El sistema solo acepta estos dominios:
- gmail.com
- hotmail.com
- outlook.com
- live.com
- yahoo.com
- icloud.com
- protonmail.com
- zoho.com
- aol.com
- gmx.com
- yandex.com
- mail.com
- fastmail.com
- tutanota.com

## ⚠️ Notas Importantes

1. **Base de Datos**: No se modificó la estructura de la BD. El sistema usa sesiones.

2. **Email**: El código se envía por email. Asegúrate de que el servidor de correo esté accesible.

3. **Timeout de Sesión**: El código expira en 15 minutos. Puedes cambiar esto en `forgot_password_view`:
   ```python
   request.session.set_expiry(timedelta(minutes=15))
   ```

4. **Requisitos de Contraseña**:
   - Mínimo 8 caracteres
   - Debe incluir letras (A-Z, a-z)
   - Debe incluir números (0-9)

## 🚀 Flujo Resumido

```
Usuario → Olvidé contraseña → Ingresa email → Recibe código por email
   ↓
Valida código → Ingresa nueva contraseña → Confirma → Éxito
   ↓
Redirige a login → Usa nuevas credenciales → ¡Listo!
```

## 🔧 Mantenimiento

### Cambiar duración del código
En `login/views.py`, línea en `forgot_password_view`:
```python
request.session.set_expiry(timedelta(minutes=15))  # Cambiar 15 al valor deseado
```

### Cambiar requisitos de contraseña
En `login/views.py`, línea en `verify_recovery_code`:
```python
if len(password) < 8:  # Cambiar 8 al mínimo deseado
```

### Cambiar dominios permitidos
En `login/views.py`, buscar `allowed_domains` y actualizar el conjunto.

---

**Estado**: ✅ FUNCIONAL Y LISTO PARA PRODUCCIÓN

No se modificó la base de datos como se solicitó.
