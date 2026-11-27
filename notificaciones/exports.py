from io import BytesIO
import os
import logging
from xml.sax.saxutils import escape

from django.http import HttpResponse, JsonResponse

from princpal.models import Sesion


logger = logging.getLogger(__name__)


DETALLE_HEADERS = [
    'Paciente',
    'Rutinas completadas/programadas',
    'Adherencia',
    'EVA promedio',
    'Variación EVA',
    'Sesiones por estado',
    'Alertas de dolor',
]
SESSION_LABELS = dict(Sesion.ESTADO_CHOICES)


def _session_summary(counts):
    return '; '.join(
        f'{SESSION_LABELS.get(state, state)}: {count}'
        for state, count in counts.items()
    )


def _patient_values(row):
    resumen = row['resumen']
    rutinas = resumen['rutinas']
    return [
        row['paciente_nombre'],
        f"{rutinas['completadas']}/{rutinas['programadas']}",
        rutinas['adherencia_pct'],
        resumen['eva']['promedio'],
        resumen['eva']['variacion'],
        _session_summary(resumen['sesiones']['por_estado']),
        resumen['alertas_dolor']['total'],
    ]


def _format_percent(value):
    return 'Sin datos' if value is None else f'{value:.2f}%'


def _format_number(value):
    return 'Sin datos' if value is None else f'{value:.2f}'


def _excel_safe_text(value):
    if value.lstrip().startswith(('=', '+', '-', '@')):
        return f"'{value}"
    return value


def _append_excel_row(sheet, values):
    sheet.append([
        _excel_safe_text(value) if isinstance(value, str) else value
        for value in values
    ])


def _attachment_response(content, content_type, payload, extension):
    inicio = payload['semana']['inicio']
    fin = payload['semana']['fin']
    filename = f'reporte-semanal-{inicio}-{fin}.{extension}'
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _dependency_error(formato, dependencia, error):
    logger.error(
        'No se pudo cargar %s para generar la exportación %s: %s',
        dependencia,
        formato,
        error,
    )
    return JsonResponse({
        'success': False,
        'error': (
            f'No se puede generar el archivo {formato}: '
            f'la dependencia {dependencia} no está disponible.'
        ),
    }, status=500)


def exportar_reporte_xlsx(payload):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        return _dependency_error('Excel', 'openpyxl', exc)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Reporte semanal'
    sheet.sheet_view.showGridLines = False

    _append_excel_row(sheet, ['Reporte semanal Nexo ReV'])
    _append_excel_row(sheet, [
        f"Semana: {payload['semana']['inicio']} al {payload['semana']['fin']}",
    ])
    _append_excel_row(sheet, [])
    _append_excel_row(sheet, ['Totales'])

    totales = payload['totales']
    summary_rows = [
        ('Pacientes', totales['pacientes']),
        ('Rutinas programadas', totales['rutinas_programadas']),
        ('Rutinas completadas', totales['rutinas_completadas']),
        ('Adherencia total', totales['adherencia_pct']),
        ('Sesiones por estado', _session_summary(totales['sesiones_por_estado'])),
        ('Alertas de dolor', totales['alertas_dolor']),
        ('Días con actividad (suma por paciente)', totales['dias_con_actividad']),
        ('Objetivos cumplidos', totales['objetivos_cumplidos']),
        ('Objetivos totales', totales['objetivos_total']),
    ]
    for label, value in summary_rows:
        _append_excel_row(sheet, [label, value if value is not None else 'Sin datos'])

    sheet['A4'].font = Font(bold=True, color='FFFFFF')
    sheet['A4'].fill = PatternFill('solid', fgColor='16745C')
    adherence_row = 4 + next(
        index for index, (label, _) in enumerate(summary_rows, start=1)
        if label == 'Adherencia total'
    )
    sheet.cell(adherence_row, 2).number_format = '0.00"%"'

    _append_excel_row(sheet, [])
    _append_excel_row(sheet, ['Detalle por paciente'])
    header_row = sheet.max_row + 1
    _append_excel_row(sheet, DETALLE_HEADERS)
    header_fill = PatternFill('solid', fgColor='16745C')
    for cell in sheet[header_row]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True, vertical='center')

    for row in payload['pacientes']:
        values = _patient_values(row)
        values[2] = values[2] if values[2] is not None else 'Sin datos'
        values[3] = values[3] if values[3] is not None else 'Sin datos'
        values[4] = values[4] if values[4] is not None else 'Sin datos'
        _append_excel_row(sheet, values)
        current_row = sheet.max_row
        sheet.cell(current_row, 3).number_format = '0.00"%"'
        for cell in sheet[current_row]:
            cell.alignment = Alignment(wrap_text=True, vertical='top')

    detail_end = sheet.max_row
    sheet.freeze_panes = f'A{header_row + 1}'
    sheet.auto_filter.ref = f'A{header_row}:G{detail_end}'
    for column, width in {
        'A': 34,
        'B': 22,
        'C': 14,
        'D': 14,
        'E': 14,
        'F': 48,
        'G': 16,
    }.items():
        sheet.column_dimensions[column].width = width
    sheet.row_dimensions[header_row].height = 32
    sheet['A1'].font = Font(size=16, bold=True, color='16745C')

    output = BytesIO()
    workbook.save(output)
    return _attachment_response(
        output.getvalue(),
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        payload,
        'xlsx',
    )


def exportar_reporte_pdf(payload):
    try:
        import reportlab
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            LongTable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        return _dependency_error('PDF', 'reportlab', exc)

    reportlab_font_dir = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
    registered_fonts = set(pdfmetrics.getRegisteredFontNames())
    if 'NexoVera' not in registered_fonts:
        pdfmetrics.registerFont(TTFont(
            'NexoVera',
            os.path.join(reportlab_font_dir, 'Vera.ttf'),
        ))
    if 'NexoVera-Bold' not in registered_fonts:
        pdfmetrics.registerFont(TTFont(
            'NexoVera-Bold',
            os.path.join(reportlab_font_dir, 'VeraBd.ttf'),
        ))
    pdfmetrics.registerFontFamily(
        'NexoVera',
        normal='NexoVera',
        bold='NexoVera-Bold',
        italic='NexoVera',
        boldItalic='NexoVera-Bold',
    )

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = 'NexoVera'
    styles['Title'].fontName = 'NexoVera-Bold'
    styles['Heading2'].fontName = 'NexoVera-Bold'
    cell_style = ParagraphStyle(
        'ReportCell',
        parent=styles['BodyText'],
        fontName='NexoVera',
        fontSize=7,
        leading=9,
        wordWrap='CJK',
        splitLongWords=1,
    )
    header_style = ParagraphStyle(
        'ReportHeader',
        parent=cell_style,
        fontName='NexoVera-Bold',
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    story = [
        Paragraph('Reporte semanal Nexo ReV', styles['Title']),
        Paragraph(
            escape(
                f"Semana: {payload['semana']['inicio']} al "
                f"{payload['semana']['fin']}"
            ),
            styles['Normal'],
        ),
        Spacer(1, 8),
        Paragraph('Totales', styles['Heading2']),
    ]

    totales = payload['totales']
    sessions_total = _session_summary(totales['sesiones_por_estado'])
    summary_rows = [
        ['Pacientes', str(totales['pacientes'])],
        [
            'Rutinas completadas/programadas',
            f"{totales['rutinas_completadas']}/{totales['rutinas_programadas']}",
        ],
        ['Adherencia total', _format_percent(totales['adherencia_pct'])],
        ['Sesiones por estado', sessions_total],
        ['Alertas de dolor', str(totales['alertas_dolor'])],
        [
            'Días con actividad (suma por paciente)',
            str(totales['dias_con_actividad']),
        ],
        [
            'Objetivos cumplidos/totales',
            f"{totales['objetivos_cumplidos']}/{totales['objetivos_total']}",
        ],
    ]
    total_table = Table(
        [
            [Paragraph(escape(label), cell_style), Paragraph(escape(value), cell_style)]
            for label, value in summary_rows
        ],
        colWidths=[72 * mm, 190 * mm],
        hAlign='LEFT',
    )
    total_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#EAF5EF')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#17382F')),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D6E3DD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([total_table, Spacer(1, 10), Paragraph('Detalle por paciente', styles['Heading2'])])

    table_data = [[
        Paragraph(escape(header), header_style)
        for header in DETALLE_HEADERS
    ]]
    for row in payload['pacientes']:
        values = _patient_values(row)
        table_data.append([
            Paragraph(escape(str(value if value is not None else 'Sin datos')), cell_style)
            for value in (
                values[0],
                values[1],
                _format_percent(values[2]),
                _format_number(values[3]),
                _format_number(values[4]),
                values[5],
                values[6],
            )
        ])

    detail_table = LongTable(
        table_data,
        colWidths=[50 * mm, 30 * mm, 24 * mm, 24 * mm, 27 * mm, 79 * mm, 20 * mm],
        repeatRows=1,
        hAlign='LEFT',
    )
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16745C')),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D6E3DD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(detail_table)
    document.build(story)
    return _attachment_response(
        buffer.getvalue(),
        'application/pdf',
        payload,
        'pdf',
    )
