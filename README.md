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

## Funcionalidades incorporadas

### Roles de paciente y médico

La aplicación diferencia entre cuentas de paciente y médico. Cada rol recibe
una experiencia adaptada y el acceso se protege mediante middleware.

### Dashboard médico y pacientes asignados

El médico puede consultar sus pacientes asignados y añadir pacientes ya
registrados o crear nuevos desde un formulario integrado. La asignación se
guarda mediante la relación `doctor_id`. Las tarjetas muestran nombre, edad,
zona afectada, estado y porcentaje de avance.

### Expediente del paciente

Al seleccionar una tarjeta, el médico consulta el expediente dentro del
apartado **Diagnóstico**, con datos, progreso, gráfica, historial de avance y
sesiones. El formulario de diagnóstico no se muestra a médicos.

### Filtros y ordenamiento

El dashboard permite mostrar únicamente pacientes de una etapa: Inicial
(0–30 %), En proceso (31–70 %), Avanzado (71–99 %) o Finalizado (100 %).
También permite ordenar por progreso, edad o nombre, de mayor a menor o de
menor a mayor. La opción **Todos** muestra nuevamente la lista completa.

### Progreso y estados visuales

El modelo `Paciente` recalcula automáticamente el estado según el avance y
conserva el historial de cambios. Los estados utilizan colores rojo, naranja,
amarillo y verde intenso.

### Mejoras de modo oscuro

Se ampliaron los estilos del modo oscuro para paneles, tarjetas, formularios,
selectores, botones, expedientes y estados, manteniendo contraste y legibilidad.

## Conexión a PostgreSQL

Para conectar la aplicación a PostgreSQL, consulta `POSTGRESQL_SETUP.md`.

## Funcionalidad videos

La aplicación permite reproducir videos locales de rehabilitación y videos
externos de YouTube desde la vista de detalle. Los videos locales utilizan un
reproductor basado en Plyr con controles de reproducción, pausa, avance,
volumen, velocidad, pantalla completa y configuración de calidad. El video se
carga con metadatos iniciales para evitar descargarlo completo antes de tiempo.

### Generación y reproducción de calidades

Cuando FFmpeg está instalado y disponible, cada video local se procesa en tres
variantes: `360p`, `480p` y `720p`. También se genera un manifiesto HLS maestro
(`master.m3u8`) compuesto por segmentos de aproximadamente seis segundos.
HLS.js carga el manifiesto en los navegadores que no reproducen HLS de forma
nativa y, en navegadores compatibles como Safari, se utiliza el soporte nativo.
Si HLS falla de forma irrecuperable, el reproductor vuelve al archivo MP4
original.

### Cambio manual de calidad

Desde **Configuración > Calidad**, la persona puede elegir `360p`, `480p` o
`720p`. El reproductor cambia la fuente correspondiente y conserva, cuando es
posible, el punto exacto de reproducción y el estado de pausa o reproducción.
El indicador sobre el reproductor muestra la calidad activa.

### Calidad automática

La opción **Automática** utiliza la fuente HLS maestra cuando el video sigue el
flujo HLS. En ese flujo, HLS.js puede escoger entre `360p`, `480p` y `720p`
según el ancho de banda y las condiciones de reproducción, reduciendo la
calidad si la conexión no permite una reproducción fluida y aumentándola cuando
mejora.

Si el video se sirve mediante fuentes MP4 derivadas, el reproductor inicia en
`720p` y permite cambiar manualmente entre ellas; `Automática` vuelve al
archivo original. Cuando no es posible generar HLS, se mantiene el MP4 original
como respaldo y no se ofrecen variantes adaptativas.

En Windows, instala FFmpeg y confirma que el siguiente comando funcione en
PowerShell antes de iniciar Django:

```powershell
ffmpeg -version
```

Después aplica la migración:

```powershell
python manage.py migrate
```

Los videos cargados antes de instalar FFmpeg seguirán usando el MP4 original;
para convertirlos a HLS hay que volver a cargarlos o ejecutar una tarea de
conversión para los registros existentes.

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
 
