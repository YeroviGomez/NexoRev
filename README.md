# NexoRev
Aplicación orientada a fisioterapia

Orden para clonar

crear entorno y activarlo
instalar django, psycopg2-binary y Pillow
clonar repositorio con git clone: url

## Configuración del correo 2FA

En desarrollo, si no se configura un correo, Django mostrará el código 2FA en
la terminal donde se ejecuta el servidor.

Para enviar códigos reales por Gmail, usa una contraseña de aplicación y define
estas variables en PowerShell antes de iniciar Django:

```powershell
$env:EMAIL_HOST_USER = 'tu-correo@gmail.com'
$env:EMAIL_HOST_PASSWORD = 'tu-contraseña-de-aplicacion'
$env:DEFAULT_FROM_EMAIL = $env:EMAIL_HOST_USER
```

No uses la contraseña normal de Gmail ni guardes estas variables en el código.

## Conexión a PostgreSQL

Para conectar la aplicación a PostgreSQL, consulta `POSTGRESQL_SETUP.md`.

aporte saul 
en dado caso la base de datos de error ejecutar en orden estos comandos dejando la tabla de ultimo mencionar que debe ser uno por uno para evitar problemas

CREATE DATABASE nexorev_db;
CREATE USER nexorev_admin WITH PASSWORD 'abcdabcdab';
GRANT ALL PRIVILEGES ON DATABASE nexorev_db TO nexorev_admin;


CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    email VARCHAR(254) UNIQUE NOT NULL,
    password VARCHAR(128) NOT NULL,
    nombre VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

GRANT ALL PRIVILEGES ON SCHEMA public TO nexorev_admin;
ALTER ROLE nexorev_admin SET search_path TO public;
-----------
si fallas al crearlo usalo si no no
DROP USER nexorev_admin;
----------
-- Dar control total sobre el esquema public
GRANT USAGE, CREATE ON SCHEMA public TO nexorev_admin;

-- Dar permisos sobre todas las tablas existentes en public
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO nexorev_admin;

-- Dar permisos sobre todas las secuencias (necesarias para SERIAL/IDENTITY)
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO nexorev_admin;

-- Dar permisos sobre todas las funciones (por si acaso)
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO nexorev_admin;

ALTER DATABASE nexorev_db OWNER TO nexorev_admin;

------- 
este bloque es para hacerte dueño de la base de datos asi tenes control total
GRANT USAGE, CREATE ON SCHEMA public TO nexorev_admin;
ALTER SCHEMA public OWNER TO nexorev_admin;
ALTER DATABASE nexorev_db OWNER TO nexorev_admin;
 
