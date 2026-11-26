from datetime import date, datetime
from functools import reduce
from operator import or_

from django.db.models import Q
from django.utils import timezone

from princpal.models import AsignacionMedico, Paciente


def asignacion_vigente(paciente):
    if not paciente or not paciente.pk or not paciente.doctor_id:
        return None
    return AsignacionMedico.objects.filter(
        paciente_id=paciente.pk,
        doctor_id=paciente.doctor_id,
        fin__isnull=True,
    ).first()


def asignaciones_vigentes_por_paciente(pacientes, doctor_id=None):
    patient_ids = [patient.pk for patient in pacientes if patient.pk]
    queryset = AsignacionMedico.objects.filter(
        paciente_id__in=patient_ids,
        fin__isnull=True,
    )
    if doctor_id is not None:
        queryset = queryset.filter(doctor_id=doctor_id)
    return {
        assignment.paciente_id: assignment
        for assignment in queryset.select_related('doctor', 'creada_por', 'creada_por_medico')
    }


def filtrar_queryset_por_asignaciones(
    queryset,
    asignaciones,
    paciente_lookup,
    fecha_lookup,
    fecha_es_solo_dia=False,
):
    conditions = []
    for paciente_id, assignment in asignaciones.items():
        if not assignment:
            continue
        filters = {paciente_lookup: paciente_id}
        cutoff = assignment.historial_clinico_visible_desde
        if cutoff is not None:
            if fecha_es_solo_dia:
                cutoff = timezone.localtime(cutoff).date()
            filters[f'{fecha_lookup}__gte'] = cutoff
        conditions.append(Q(**filters))
    if not conditions:
        return queryset.none()
    return queryset.filter(reduce(or_, conditions))


def historial_avance_visible(paciente, assignment):
    history = list(paciente.historial_avance or [])
    if not assignment:
        return []
    cutoff = assignment.historial_clinico_visible_desde
    if cutoff is None:
        return history or paciente.get_progress_series()

    visible = []
    for point in history:
        value = point.get('fecha')
        if not value:
            continue
        try:
            point_date = datetime.fromisoformat(str(value))
        except ValueError:
            try:
                point_date = date.fromisoformat(str(value))
            except ValueError:
                continue
        if isinstance(point_date, datetime):
            if timezone.is_naive(point_date):
                point_date = timezone.make_aware(point_date)
            if point_date >= cutoff:
                visible.append(point)
        elif point_date >= timezone.localtime(cutoff).date():
            visible.append(point)
    return visible


def progreso_visible(paciente, assignment):
    if not assignment:
        avance = 0
    elif assignment.historial_clinico_visible_desde is None:
        avance = paciente.avance
    else:
        history = historial_avance_visible(paciente, assignment)
        avance = int(history[-1].get('avance', 0)) if history else 0

    if avance >= 100:
        estado = Paciente.ESTADO_FINALIZADO
    elif avance >= 71:
        estado = Paciente.ESTADO_AVANZADO
    elif avance >= 31:
        estado = Paciente.ESTADO_EN_PROCESO
    else:
        estado = Paciente.ESTADO_INICIAL
    return avance, estado
