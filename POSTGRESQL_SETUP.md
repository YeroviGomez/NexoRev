# Conectar Django con PostgreSQL

Esta guía explica cómo configurar tu proyecto Django para usar una base de datos PostgreSQL en lugar de SQLite.

## 1. Instalar PostgreSQL

1. Descarga e instala PostgreSQL desde https://www.postgresql.org/download/windows/.
2. Durante la instalación, crea una contraseña para el usuario `postgres`.
3. Usa pgAdmin o la consola `psql` para crear la base de datos y el usuario:

```sql
CREATE DATABASE nexorev_db;
CREATE USER nexorev_user WITH PASSWORD 'abcdabcdab';
GRANT ALL PRIVILEGES ON DATABASE nexorev_db TO nexorev_user;
```

4. Crea la tabla para el login de usuarios. En este ejemplo usamos correo y contraseña:

```sql
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    email VARCHAR(254) UNIQUE NOT NULL,
    password VARCHAR(128) NOT NULL,
    nombre VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

> Importante: guarda las contraseñas en la base de datos como hashes seguros, no texto claro.

### 4.1 Insertar datos en la tabla

Hacer `makemigrations` y `migrate` crea la estructura de la tabla, pero no inserta datos automáticamente. Para ver filas en la tabla debes crear registros manualmente.

Ejemplo SQL de inserción básica:

```sql
INSERT INTO usuarios (email, password, nombre)
VALUES ('usuario@dominio.com', 'tu_contraseña_hasheada', 'Usuario Prueba');
```

Ejemplo usando el ORM de Django (preferido si ya tienes el modelo `Usuario`):

```powershell
python manage.py shell
```

```python
from crear_cuenta.models import Usuario
usuario = Usuario(email='usuario@dominio.com', nombre='Usuario Prueba')
usuario.set_password('tu_contraseña_segura')
usuario.save()
```

Si prefieres insertar datos desde la consola SQL, recuerda que la contraseña debe estar hasheada si tu app la valida con `check_password()`.

## 2. Instalar la librería de Python

Activa el entorno virtual de tu proyecto y ejecuta:

```powershell
cd c:\Users\Yerovi\Desktop\NexoRev\env\NexoRev
..\Scripts\Activate.ps1
pip install psycopg2-binary
```

> Si prefieres no usar `psycopg2-binary`, puedes instalar `psycopg2` con compilación local, pero en Windows `psycopg2-binary` suele ser más sencillo.

## 3. Configurar `settings.py`

Abre `NexoRev\NexoRev\settings.py` y modifica la sección `DATABASES` para usar PostgreSQL:

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ... otras configuraciones ...

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'nexorev_db'),
        'USER': os.environ.get('POSTGRES_USER', 'nexorev_admin'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'abcdabcdab'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}
```

## 4. Variables de entorno opcionales

Puedes definir variables de entorno en PowerShell para no dejar datos sensibles en el código fuente:

```powershell
$env:POSTGRES_DB = 'nexorev_db'
$env:POSTGRES_USER = 'nexorev_user'
$env:POSTGRES_PASSWORD = 'tu_contraseña_segura'
$env:POSTGRES_HOST = 'localhost'
$env:POSTGRES_PORT = '5432'
```

Si prefieres, usa un archivo `.env` con `python-dotenv` y carga esos valores en `settings.py`.

## 5. Ejecutar migraciones

Después de guardar los cambios, ejecuta:

```powershell
python manage.py migrate
```

## 6. Verificar la conexión

Inicia el servidor de Django y asegúrate de que no hay errores de conexión:

```powershell
python manage.py runserver
```

Si ves errores relacionados con PostgreSQL, revisa:

- que el servidor PostgreSQL esté en marcha
- que el nombre de la base de datos, usuario y contraseña sean correctos
- que el puerto `5432` esté disponible

## 7. Notas adicionales

- Si trabajas con Docker o con otra máquina, cambia `HOST` al nombre del contenedor o IP correspondiente.
- Para producción, no uses `psycopg2-binary`; usa `psycopg2` con una instalación más estable.
