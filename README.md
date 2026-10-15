# NexoRev
Aplicación orientada a fisioterapia

Orden para clonar

crear entorno y activarlo
instalar django, psycopg2-binary y Pillow
clonar repositorio con git clone: url

## Configuración del correo

En desarrollo, si no se configuran credenciales de correo, Django usa el
backend de consola: el código 2FA y el aviso de inicio de sesión se muestran
como correos en la terminal donde se ejecuta el servidor. El aviso se envía
únicamente después de completar correctamente la verificación 2FA.

Para enviar correos reales por Gmail, usa una contraseña de aplicación y define
estas variables en PowerShell antes de iniciar Django. Al detectar ambas
credenciales, Django usa SMTP automáticamente:

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

El médico puede consultar sus pacientes asignados en un dashboard con métricas
de pacientes activos, avance promedio, dolor EVA y cumplimiento de objetivos.
Incluye tablas y gráficas de evolución del dolor, objetivos, adherencia a
sesiones, progreso por paciente y valores clínicos frente a sus metas. Los
filtros permiten seleccionar paciente, fechas y estado del tratamiento, y la
tabla se puede ordenar por progreso, sesiones realizadas o última sesión.

Las evaluaciones históricas y objetivos se guardan en `EvaluacionClinica` y
`ObjetivoTerapeutico`. Desde el dashboard se pueden registrar evaluaciones
clínicas, definir objetivos, agendar sesiones y marcar citas vencidas como
realizadas. Cada objetivo permite indicar si se cumple al alcanzar/superar la
meta o al reducir la métrica hasta ese valor. Las gráficas consultan la base
de datos y se refrescan automáticamente cada minuto. La asignación se guarda
mediante `doctor_id` y los endpoints del dashboard limitan la consulta y
escritura al especialista asignado.

Los datos antiguos de dolor disponibles en el diagnóstico del paciente se
utilizan como punto histórico cuando aún no hay evaluaciones clínicas nuevas.
La comparación de objetivos toma la evaluación más reciente de la misma
métrica y unidad.

### Preguntas de seguridad

Desde **Perfil → Seguridad de la cuenta**, cada usuario puede configurar al
menos dos preguntas predefinidas o personalizadas. Las respuestas se normalizan
y almacenan con hash; no se muestran en la interfaz ni se incluyen en las
respuestas de la API. Para las cuentas que tengan preguntas configuradas, la
recuperación de contraseña requiere verificar el código enviado por correo y
responder correctamente todas las preguntas. Los errores de código o de
respuesta se registran sin almacenar las respuestas y limitan la recuperación
a cinco intentos por correo en una ventana de 15 minutos. Las cuentas sin
preguntas conservan la recuperación por código para no bloquear a usuarios
existentes.

### Mi Progreso del paciente

La vista del paciente reúne la etapa del tratamiento, historial gráfico,
objetivos que cumplen las evaluaciones clínicas, sesiones programadas y
rutinas asignadas. El porcentaje general es el promedio de cuatro porcentajes:
objetivos cumplidos, sesiones realizadas, rutinas asignadas vencidas o
programadas para hoy que se completaron y evaluaciones con reducción del dolor
frente a la evaluación anterior. Un componente sin registros aporta 0 %.

El fisioterapeuta asigna videos de ejercicio a pacientes propios desde el
dashboard, con una fecha. Al marcarse un video como completado se actualiza la
asignación correspondiente; se conserva el historial de avances en el paciente.
La vista consulta los datos actuales y los refresca periódicamente, incluso
cuando se registran sesiones o evaluaciones desde otra sesión.

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
 
