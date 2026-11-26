from django.db.models import F

from crear_cuenta.models import Usuario
from princpal.models import AsignacionMedico, Paciente


def usuario_de_sesion(session):
    email = session.get('current_user')
    if not email:
        return None

    usuario = Usuario.objects.filter(email=email, is_active=True).first()
    if not usuario or session.get('current_user_role') != usuario.role:
        return None
    return usuario


def tiene_acceso_a_paciente(user, paciente):
    if isinstance(user, Usuario):
        authenticated = bool(user.pk and user.is_active)
    else:
        authenticated = bool(getattr(user, 'is_authenticated', False))

    if not authenticated or not paciente.usuario_id or not paciente.doctor_id:
        return False
    asignacion_activa = AsignacionMedico.objects.filter(
        paciente_id=paciente.pk,
        doctor_id=paciente.doctor_id,
        fin__isnull=True,
    ).exists()
    if not asignacion_activa:
        return False
    return (
        user.pk == paciente.usuario_id and user.role == Usuario.ROLE_PACIENTE
    ) or (
        user.pk == paciente.doctor_id and user.role == Usuario.ROLE_DOCTOR
    )


def pacientes_conversables(user):
    if not isinstance(user, Usuario) or not user.pk or not user.is_active:
        return Paciente.objects.none()
    if user.role == Usuario.ROLE_PACIENTE:
        return Paciente.objects.filter(
            usuario=user,
            doctor__isnull=False,
            asignaciones__doctor_id=F('doctor_id'),
            asignaciones__fin__isnull=True,
        )
    if user.role == Usuario.ROLE_DOCTOR:
        return Paciente.objects.filter(
            doctor=user,
            usuario__isnull=False,
            asignaciones__doctor=user,
            asignaciones__fin__isnull=True,
        )
    return Paciente.objects.none()
