from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)

class SlideSlidePartner(models.Model):
    _inherit = 'slide.slide.partner'

    channel_partner_id = fields.Many2one(
        'slide.channel.partner', 
        string='Inscripción en Curso',
        compute='_compute_channel_partner_id',
        store=True,
        ondelete='set null'# Evitamos que el alumno pierda su historial en caso de que se borre el curso o se desmatricule.
    )

    estado_evaluacion = fields.Selection([
        ('pendiente_presentar', 'Pendiente de Presentar'),
        ('pendiente_revision', 'Pendiente de Revisión'),
        ('evaluado', 'Evaluado')
    ], string='Estado de Evaluación', default='pendiente_presentar', required=True)

    nota_evaluacion = fields.Float(string='Nota', default=0.0, digits=(16, 2))
    
    # --- Gestión de Entregas (Archivos) ---
    archivo_entrega = fields.Binary("Archivo Entregado")
    nombre_archivo = fields.Char("Nombre del Archivo")
    fecha_entrega = fields.Datetime("Fecha de Presentación")

    # --- Campos Relacionados (UI Helpers) ---
    es_evaluable = fields.Boolean(related='slide_id.es_evaluable', string="¿Es Evaluable?", readonly=True)
    slide_category = fields.Selection(related='slide_id.slide_category', string="Categoría", readonly=True)

    @api.constrains('nota_evaluacion')
    def _check_nota(self):
        for record in self:
            if record.nota_evaluacion < 0 or record.nota_evaluacion > 10:
                raise ValidationError("La nota debe estar entre 0 y 10")

    def accion_confirmar_nota(self):
        """ El profesor confirma que la nota del contenido es definitiva """
        for record in self:
            # Eliminadas validaciones restrictivas para permitir Feedback manual en cualquier estado/tipo
            record.estado_evaluacion = 'evaluado'

    @api.depends('channel_id', 'partner_id')
    def _compute_channel_partner_id(self):
        for record in self:
            if record.channel_id and record.partner_id:
                # Buscamos la inscripción que coincida con el curso y el alumno
                record.channel_partner_id = self.env['slide.channel.partner'].search([
                    ('channel_id', '=', record.channel_id.id),
                    ('partner_id', '=', record.partner_id.id)
                ], limit=1)
            else:
                record.channel_partner_id = False

    def write(self, vals):
        # Bloqueo de Modificación de Notas
        if 'nota_evaluacion' in vals:
            for record in self:
                # 1. Si el contenido ya está evaluado y confirmado (salvo que estemos reabriendo el estado en la misma escritura)
                if record.estado_evaluacion == 'evaluado' and vals.get('estado_evaluacion') != 'pendiente_revision':
                    raise ValidationError("No se puede modificar la nota de un contenido que ya está marcado como Evaluado.")
                
                # 2. Si el Acta del Curso está cerrada
                if record.channel_partner_id.estado_nota in ['evaluado', 'pendiente_certificar', 'certificado']:
                    raise ValidationError("No se puede modificar notas porque el Acta del Curso está cerrada.")

        # Automatización: Si el slide se marca como completado, calculamos nota si es Quiz o Certificación
        if vals.get('completed'):
            for record in self:
                if record.slide_id.es_evaluable and record.estado_evaluacion == 'pendiente_presentar':
                    # 1. Certificaciones y Exámenes (Survey)
                    if record.slide_id.slide_category == 'exam' and record.slide_id.survey_id:
                         # Para Exámenes: Tomamos el último intento finalizado (sea aprobado o no)
                         user_input = self.env['survey.user_input'].search([
                            ('survey_id', '=', record.slide_id.survey_id.id),
                            ('partner_id', '=', record.partner_id.id),
                            ('state', '=', 'done')
                        ], limit=1, order='create_date desc')
                         if user_input:
                            vals['nota_evaluacion'] = round((user_input.scoring_percentage / 100.0) * 10, 2)
                            vals['estado_evaluacion'] = 'evaluado' # AUTOMÁTICO
                            vals['fecha_entrega'] = fields.Datetime.now()
 
                    elif record.slide_id.slide_category == 'certification' and record.slide_id.survey_id:
                        user_input = self.env['survey.user_input'].search([
                            ('survey_id', '=', record.slide_id.survey_id.id),
                            ('partner_id', '=', record.partner_id.id),
                            ('scoring_success', '=', True)
                        ], limit=1, order='create_date desc')
                        if user_input:
                            vals['nota_evaluacion'] = round((user_input.scoring_percentage / 100.0) * 10, 2)
                            vals['estado_evaluacion'] = 'evaluado' # AUTOMÁTICO
                            vals['fecha_entrega'] = fields.Datetime.now()
        
        # Si se sube un archivo, pasamos a Pendiente de Revisión
        if 'archivo_entrega' in vals and vals.get('archivo_entrega'):
            vals['estado_evaluacion'] = 'pendiente_revision'
            vals['fecha_entrega'] = fields.Datetime.now()
 
        return super().write(vals)

class SlideChannelPartner(models.Model):
    _name = 'slide.channel.partner'
    _inherit = ['slide.channel.partner', 'mail.thread', 'mail.activity.mixin']

    @api.model_create_multi
    def create(self, vals_list):
        """ Sobrescribimos create para evitar que el responsable del curso se inscriba automáticamente como alumno """
        # Optimización: Cargar canales en lote
        channel_ids = {v.get('channel_id') for v in vals_list if v.get('channel_id')}
        channels = self.env['slide.channel'].browse(channel_ids)
        channel_resp_map = {c.id: c.user_id.partner_id.id for c in channels}
        
        vals_filtrados = []
        for vals in vals_list:
            cid = vals.get('channel_id')
            pid = vals.get('partner_id')
            
            # Filtro: Si el partner a inscribir es el responsable del canal, lo omitimos
            if cid and pid and cid in channel_resp_map:
                if channel_resp_map[cid] == pid:
                    continue
            
            vals_filtrados.append(vals)
            
        if not vals_filtrados:
            return self.env['slide.channel.partner'] # Retorno vacío si filtra todo
            
        return super().create(vals_filtrados)

    def write(self, vals):
        res = super().write(vals)
        
        # PROPAGACIÓN ASCENDENTE: Si cambia la nota de una asignatura, avisar al Master
        if 'nota_final' in vals:
            for record in self:
                if record.channel_id.tipo_curso == 'asignatura' and record.channel_id.master_id:
                    # Buscamos la inscripción del alumno en el Master padre
                    master_enrollment = self.search([
                        ('channel_id', '=', record.channel_id.master_id.id),
                        ('partner_id', '=', record.partner_id.id)
                    ], limit=1)
                    
                    if master_enrollment:
                        master_enrollment._compute_nota_academica()
        return res



    today = fields.Date.today()
    
    # --- UI Helpers ---
    tiene_titulo_curso = fields.Boolean(related='channel_id.tiene_titulo', string="Curso emite título", readonly=True)
    tipo_curso_rel = fields.Selection(related='channel_id.tipo_curso', string="Tipo de Curso (Rel)", readonly=True)

    # --- Notas y Estados ---
    nota_final = fields.Float(
        string='Nota Académica', 
        compute='_compute_nota_academica', 
        store=True, 
        readonly=False,
        digits=(16, 2),
        aggregator='avg'
    )
    
    estado_nota = fields.Selection([
        ('pendiente_revision', 'Pendiente'),
        ('evaluado', 'Evaluado'),
        ('pendiente_certificar', 'Título Pendiente de Emitir'),
        ('certificado', 'Título Emitido')
    ], string='Estado Acta', default='pendiente_revision', required=True)

    # --- Tracking de Certificación ---
    titulo_emitido = fields.Boolean(string="Título Generado", default=False, readonly=True)
    fecha_emision_titulo = fields.Datetime(string="Fecha de Emisión", readonly=True)
    survey_user_input_id = fields.Many2one('survey.user_input', string="Certificación Vinculada", readonly=True)

    nota_manual = fields.Boolean(
        string='Corrección Manual', 
        default=False,
        help="Si se marca, el profesor puede sobreescribir la nota autocalculada."
    )

    can_grade_manually = fields.Boolean(
        string='Permiso Corrección Manual',
        compute='_compute_can_grade_manually'
    )

    @api.depends('channel_id', 'channel_id.tipo_curso')
    def _compute_can_grade_manually(self):
        user = self.env.user
        is_admin = user.has_group('elearning_universidad.grupo_administrador_universidad') or user.has_group('base.group_system')
        
        for record in self:
            if is_admin:
                record.can_grade_manually = True
                continue

            # Directores siempre pueden en sus cursos
            if user.id in record.channel_id.director_academico_ids.ids:
                record.can_grade_manually = True
                continue

            # Docentes SOLO en asignaturas
            if record.channel_id.tipo_curso == 'asignatura' and user.id in record.channel_id.personal_docente_ids.ids:
                record.can_grade_manually = True
            else:
                record.can_grade_manually = False

    # Relación para acceder a las evaluaciones de contenidos desde el boletín
    # CAMBIO: Mostramos TODOS los tipos relevantes (Examen, Entregable, etc) aunque no sean evaluables
    evaluaciones_ids = fields.One2many(
        'slide.slide.partner', 
        'channel_partner_id', 
        string='Evaluaciones de Contenido',
        domain=['&', ('slide_id.is_published', '=', True), '|', ('slide_id.es_evaluable', '=', True), ('slide_id.slide_category', 'in', ['exam', 'delivery', 'certification', 'sub_course'])]
    )

    # --- Jerarquía y Navegación (Master -> Asignaturas) ---
    # Smart Grouping: Si es Master, se agrupa consigo mismo. Si es Asignatura, con su Master.
    gradebook_master_id = fields.Many2one('slide.channel', string='Agrupación (Master)', compute='_compute_gradebook_master_id', store=True)
    
    @api.depends('channel_id.master_id', 'channel_id.tipo_curso')
    def _compute_gradebook_master_id(self):
        for record in self:
            if record.channel_id.tipo_curso == 'master':
                record.gradebook_master_id = record.channel_id
            else:
                record.gradebook_master_id = record.channel_id.master_id

    asignatura_partner_ids = fields.One2many(
        'slide.channel.partner', 
        compute='_compute_asignatura_partner_ids', 
        inverse='_set_asignatura_partner_ids', # Necesario para que el popup sea editable
        string='Asignaturas dadas por este alumno en este Master'
    )

    def _set_asignatura_partner_ids(self):
        """ Método inverse dummy para permitir edición en el popup One2many """
        pass

    @api.depends('channel_id', 'partner_id')
    def _compute_asignatura_partner_ids(self):
        # Obtener el usuario actual para filtrar visibilidad
        current_user = self.env.user
        is_admin = current_user.has_group('elearning_universidad.grupo_administrador_universidad') or current_user.has_group('base.group_system')

        for record in self:
            if record.channel_id.tipo_curso == 'master':
                domain = [
                    ('partner_id', '=', record.partner_id.id),
                    ('channel_id.master_id', '=', record.channel_id.id),
                    ('channel_id.tipo_curso', '=', 'asignatura'),
                    ('channel_id.estado_universidad', '=', 'publicado')
                ]
                
                # FILTRO DE SEGURIDAD: 
                # 1. Si soy Admin, veo todo.
                # 2. Si soy el PROPIO ALUMNO viendo mis notas (Portal), veo todo.
                # 3. Si soy un Docente viendo a un alumno, solo veo las asignaturas que imparto.
                
                is_student_self = (record.partner_id == current_user.partner_id)
                
                if not is_admin and not is_student_self:
                    domain += ['|', ('channel_id.director_academico_ids', 'in', current_user.id), ('channel_id.personal_docente_ids', 'in', current_user.id)]

                record.asignatura_partner_ids = self.search(domain)
            else:
                record.asignatura_partner_ids = False

    @api.depends(
        'channel_id.tipo_curso', 
        'nota_manual',
        'evaluaciones_ids.nota_evaluacion', 
        'evaluaciones_ids.estado_evaluacion',
        'channel_id.asignatura_ids.total_time'
    )
    def _compute_nota_academica(self):
        # 1. Separamos registros manuales (no se calculan)
        auto_records = self.filtered(lambda r: not r.nota_manual)
        
        # 2. Separamos por tipo para optimizar
        masters_records = auto_records.filtered(lambda r: r.channel_id.tipo_curso == 'master')
        others_records = auto_records - masters_records # Asignatura, Microcredencial
        
        # 3. Procesamiento Estándar (Otros)
        # Odoo prefetch maneja bien las evaluaciones_ids si iteramos
        for record in others_records:
            # FILTRO: Solo calculamos media de los contenidos marcados como 'es_evaluable'
            # Permitimos que el profesor evalúe los otros (feedback), pero no suman.
            evals = record.evaluaciones_ids.filtered(lambda x: x.slide_id.es_evaluable)
            if evals:
                record.nota_final = round(sum(evals.mapped('nota_evaluacion')) / len(evals), 2)
            else:
                record.nota_final = 0.0
        
        # 4. Procesamiento Masters (Optimizado: Batch)
        if not masters_records:
            return

        # Recopilación de datos masiva
        all_masters = masters_records.mapped('channel_id')
        all_asignaturas = all_masters.mapped('asignatura_ids')
        all_partners = masters_records.mapped('partner_id')
        
        # Búsqueda ÚNICA de todas las sub-inscripciones relevantes
        if all_asignaturas and all_partners:
            domain = [
                ('channel_id', 'in', all_asignaturas.ids),
                ('partner_id', 'in', all_partners.ids)
            ]
            # Usamos read_group si solo quisieramos datos, pero necesitamos nota_final que es computado. 
            # Search normal es mejor que loop.
            sub_inscriptions = self.env['slide.channel.partner'].search(domain)
            
            # Mapeo en Memoria: (partner_id, channel_id) -> nota_final
            scores_map = {(i.partner_id.id, i.channel_id.id): i.nota_final for i in sub_inscriptions}
        else:
            scores_map = {}

        # Pre-cálculo de datos de Masters para evitar re-sumar horas en cada alumno
        master_data_cache = {}
        for master in all_masters:
             # Búsqueda de los slides tipo 'sub_course' (Asignaturas) dentro del Master
             # Estos contienen la duración OFICIAL para la ponderación académica.
             master_slides = self.env['slide.slide'].search([
                 ('channel_id', '=', master.id),
                 ('slide_category', '=', 'sub_course')
             ])
             
             # Mapa: ID del Canal Asignatura -> Duración (Slide)
             # Esto permite buscar rápido la duración de una asignatura dado su canal_id
             duration_map = {s.asignatura_id.id: s.completion_time for s in master_slides if s.asignatura_id}
             
             total_horas = sum(duration_map.values())
             master_data_cache[master.id] = {
                 'asignaturas': master.asignatura_ids, # Mantenemos referencia para iterar
                 'duration_map': duration_map,
                 'total_horas': total_horas if total_horas > 0 else 0
             }

        # Cálculo Final en Memoria
        for record in masters_records:
            m_data = master_data_cache.get(record.channel_id.id)
            
            total_horas_master = m_data['total_horas'] if m_data else 0
            asignaturas = m_data['asignaturas'] if m_data else []
            duration_map = m_data['duration_map'] if m_data else {}
            
            if not asignaturas:
                 record.nota_final = 0.0
                 continue

            nota_acumulada = 0.0
            
            if total_horas_master > 0:
                # Media Ponderada por Horas (DEFINIDAS EN EL MASTER)
                for asig in asignaturas:
                    nota_asig = scores_map.get((record.partner_id.id, asig.id), 0.0)
                    # Recuperamos la duración oficial del slide asociado a esta asignatura
                    asig_duration = duration_map.get(asig.id, 0.0)
                    
                    peso = asig_duration / total_horas_master
                    nota_acumulada += nota_asig * peso
            else:
                # Media Aritmética Simple (Fallback si no hay horas definidas)
                count = len(asignaturas)
                for asig in asignaturas:
                    nota_asig = scores_map.get((record.partner_id.id, asig.id), 0.0)
                    nota_acumulada += nota_asig
                nota_acumulada = nota_acumulada / count if count > 0 else 0.0
            
            record.nota_final = round(nota_acumulada, 2)

    def accion_cerrar_acta(self):
        """ Cierra la nota final del curso/asignatura y dispara la certificación si procede """
        for record in self:
            tipo = record.channel_id.tipo_curso
            
            if tipo in ['asignatura', 'microcredencial']:
                # No se puede cerrar si hay contenidos evaluables sin confirmar como evaluado
                if any(ev.estado_evaluacion != 'evaluado' for ev in record.evaluaciones_ids):
                    raise ValidationError("Debe evaluar y cerrar todas las notas de los contenidos evaluables antes de cerrar la asignatura.")
            
            elif tipo == 'master':
                # No se puede cerrar si hay asignaturas sin confirmar como evaluado
                asignaturas = record.channel_id.asignatura_ids
                for asig in asignaturas:
                    insc_asig = self.env['slide.channel.partner'].search([
                        ('channel_id', '=', asig.id),
                        ('partner_id', '=', record.partner_id.id)
                    ], limit=1)
                    if not insc_asig or insc_asig.estado_nota != 'evaluado':
                        raise ValidationError(f"La asignatura '{asig.name}' aún no ha sido evaluada y cerrada para este alumno.")
            
            # Cambiamos a evaluado
            record.estado_nota = 'evaluado'
            
            # Si el curso emite título y el alumno ha aprobado
            if record.channel_id.tiene_titulo and record.nota_final >= 5.0 and not record.titulo_emitido:
                # POLITICA DE EMISION:
                # Automática: Pasa directo a 'pendiente_certificar' (para que el CRON lo recoja)
                # Manual: Se queda en 'evaluado', esperando que el admin pulse "Emitir Título"
                if record.channel_id.politica_emision == 'automatica':
                    record.estado_nota = 'pendiente_certificar'

    def action_issue_university_degree(self):
        """ Emisión manual de títulos universitarios (Paso a cola de emisión) """
        self.ensure_one()
        # CASO 1: Si pulsamos el botón en estado 'evaluado' (flujo manual), lo pasamos a cola
        if self.estado_nota == 'evaluado':
             if self.nota_final < 5.0:
                raise ValidationError("El alumno no ha superado satisfactoriamente el curso (Nota < 5.0).")
             
             self.estado_nota = 'pendiente_certificar'
             return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Encolado para Emisión',
                    'message': f'El título para {self.partner_id.name} se ha puesto en cola. Se generará en breves momentos.',
                    'type': 'success',
                }
            }
        
        # CASO 2: Si por alguna razón forzamos la regeneración (ya certificado o pendiente)
        # Dejamos que el CRON o una acción explícita 'force_generate' lo maneje.
        # Por ahora, el comportamiento estándar del botón es "Aprobar emisión".
        return

    @api.model
    def _cron_emitir_titulos_pendientes(self):
        """ CRON para emitir títulos de alumnos aptos de forma asíncrona y generar PDF """
        inscripciones = self.search([
            ('estado_nota', '=', 'pendiente_certificar'),
            ('titulo_emitido', '=', False)
        ], limit=50) 
        
        for inscripcion in inscripciones:
            try:
                # 1. Generar PDF usando el layout seleccionado en el curso
                layout = inscripcion.channel_id.plantilla_titulo or 'modern_gold'
                
                # Creamos un survey.user_input FAKE o usamos uno existente si hubiera
                # Pero para simplificar, usaremos el motor de reportes de Survey directamente si es posible,
                # o simularemos los datos que espera la plantilla.
                # Las plantillas de certificación de Odoo esperan un objeto 'survey.user_input'.
                # Si no tenemos uno real (porque es un Master sin examen final tipo survey), debemos crear uno dummy
                # o adaptar la llamada.
                
                # ESTRATEGIA: Crear un registro dummy en survey.user_input asociado a una certificación "virtual"
                # O reutilizar el mecanismo de renderizado. 
                # Para ser robustos y usar el estándar, crearemos un input temporal asociado a los datos del curso.
                
                # Problema: Necesitamos un survey_id. 
                # Solución: Si el curso tiene un slide tipo 'certification', usamos ese survey.
                # Si NO (ej. un Master calificado por asignaturas), necesitamos una "Certificación Genérica" o crear el PDF manualmente.
                # EL USUARIO DIJO: "ya en las opciones del curso seleccione emitir titulo y seleccione la plantilla".
                # Odoo por defecto asocia la plantilla AL SURVEY. Si el usuario lo seleccionó EN EL CURSO, 
                # es un custom field nuestro 'plantilla_titulo'.
                
                # Vamos a usar el report 'survey.certification_report' pasando IDs de slide.channel.partner
                # PERO ese reporte espera 'survey.user_input'.
                # TRAMPA: Heredaremos o crearemos un reporte propio que acepte slide.channel.partner?
                # NO. El usuario quiere "usar las plantillas de certificados".
                
                # OPCIÓN VIABLE: Renderizar la plantilla QWEB directamente pasando los valores en 'docs'.
                # Las plantillas qweb de survey (ej. survey_certification_report_view.xml) usan 'user_input' como variable.
                # Podemos pasar un objeto Mock que tenga los campos que la plantilla usa (partner_id, scoring_percentage, test_entry, etc.)
                
                # MOCK CLASS local para engañar a la plantilla QWeb
                class CertificationMock:
                    def __init__(self, partner, channel, score, date, layout):
                        self.partner_id = partner
                        self.scoring_percentage = score * 10 # Sobre 100
                        self.scoring_total = 100
                        self.survey_id = type('obj', (object,), {'title': channel.name, 'certification_report_layout': layout})
                        self.test_entry = False # Para que no salga "Test"
                        self.create_date = date
                        self.user_input_line_ids = [] # Sin respuestas detalladas
                        
                mock_input = CertificationMock(
                    inscripcion.partner_id, 
                    inscripcion.channel_id, 
                    inscripcion.nota_final, 
                    fields.Datetime.now(),
                    layout
                )
                
                # Renderizar PDF (Binario)
                # Odoo 16/17 usa _render_qweb_pdf. El nombre del report externo suele ser 'survey.certification_report'.
                # Pero al pasar un objeto custom, la llamada estándar ir.actions.report no funcionará directo con IDs.
                # Debemos renderizar el HTML y luego PDF.
                
                # HACK MEJORADO: ¿Y si creamos un survey.user_input REAL?
                # Es más seguro para persistencia.
                # 1. Buscamos/Creamos un survey "wrapper" para el título del Master (si no existe)
                # 1. Buscamos/Creamos un survey "wrapper" para el título del Master (si no existe)
                # Usamos el nombre exacto del curso para que en el certificado salga bien (ej. "Master en Data Science")
                survey_title = inscripcion.channel_id.name
                survey = self.env['survey.survey'].sudo().search([('title', '=', survey_title)], limit=1)
                
                if not survey:
                    survey = self.env['survey.survey'].sudo().create({
                        'title': survey_title,
                        'certification': True,
                        'scoring_type': 'scoring_without_answers', # Odoo a veces re-computa
                        'certification_report_layout': layout,
                        'scoring_success_min': 0.0, 
                    })
                
                # HACK: Asegurar que el survey tenga AL MENOS una pregunta puntuable, 
                # de lo contrario scoring_percentage siempre será 0 (Odoo lo calcula sobre el total de puntos posibles)
                # Si el survey es nuevo o no tiene preguntas, creamos una oculta.
                if not survey.question_ids:
                    self.env['survey.question'].sudo().create({
                        'survey_id': survey.id,
                        'title': 'Nota de Expediente',
                        'question_type': 'numerical_box',
                        'answer_score': 10.0, # Max score 10
                        'is_scored_question': True,
                        'sequence': 0,
                    })

                # Asegurar que el layout es el correcto si cambiaron la configuración
                if survey.certification_report_layout != layout:
                    survey.write({'certification_report_layout': layout})

                # 2. Creamos el input finalizado
                user_input = self.env['survey.user_input'].sudo().create({
                    'survey_id': survey.id,
                    'partner_id': inscripcion.partner_id.id,
                    'state': 'done',
                })

                # 3. Crear línea de respuesta para forzar la nota de forma natural
                # Buscamos la pregunta puntuable (la que acabamos de crear o la que hubiera)
                question = survey.question_ids[0]
                self.env['survey.user_input.line'].sudo().create({
                    'user_input_id': user_input.id,
                    'question_id': question.id,
                    'answer_type': 'numerical_box',
                    'value_numerical_box': inscripcion.nota_final, # Ej. 8.5
                    'answer_score': inscripcion.nota_final # Esto Odoo lo usa para sumar
                })
                
                # Forzamos Success por seguridad (aunque el min=0 debería bastar) y recalcualamos
                # Odoo debería calcular scoring_percentage = (8.5 / 10) * 100 = 85.0
                user_input.write({'scoring_success': True})
                
                # 3. Generar PDF (Con contexto de IDIOMA del alumno)
                # Importante: Pasar el contexto en la llamada
                pdf_content, _ = self.env['ir.actions.report'].with_context(lang=inscripcion.partner_id.lang).sudo()._render_qweb_pdf(
                    'survey.certification_report', 
                    [user_input.id],
                    data={'report_type': 'pdf'}
                )
                
                # 4. Adjuntar al registro de inscripción
                filename = f"Titulo_{inscripcion.channel_id.name}_{inscripcion.partner_id.name}.pdf".replace(" ", "_")
                attachment = self.env['ir.attachment'].create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'slide.channel.partner',
                    'res_id': inscripcion.id,
                    'mimetype': 'application/pdf'
                })
                
                # 5. Guardar referencia y actualizar estado
                inscripcion.sudo().write({
                    'estado_nota': 'certificado',
                    'titulo_emitido': True,
                    'fecha_emision_titulo': fields.Datetime.now(),
                    'survey_user_input_id': user_input.id 
                })
                
            except Exception as e:
                # Log error
                _logger.error(f"Error generando título para {inscripcion.id}: {str(e)}")
                continue

    def action_download_certificate(self):
        """ Acción para descargar el certificado PDF adjunto """
        self.ensure_one()
        # Buscar el adjunto más reciente generado para este modelo y ID
        # Se asume que el nombre comienza con "Titulo_" o simplemente el último PDF adjunto
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'slide.channel.partner'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf')
        ], order='create_date desc', limit=1)

        if not attachment:
             # Si no hay adjunto, lanzamos notificación
             return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Certificado no encontrado',
                    'message': 'No se ha encontrado el archivo PDF del certificado. Contacte con administración.',
                    'type': 'warning',
                }
            }
        
        # Redirigir a la URL de descarga directa
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_regenerate_certificate(self):
        """ Permite a un administrador regenerar el título si hubo un error """
        self.ensure_one()
        if not self.env.user.has_group('elearning_universidad.grupo_administrador_universidad'):
             raise ValidationError("Solo los administradores pueden regenerar títulos.")
        
        # Eliminamos adjuntos previos de tipo PDF para evitar confusión
        adjuntos = self.env['ir.attachment'].search([
            ('res_model', '=', 'slide.channel.partner'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'application/pdf'),
            ('name', 'like', 'Titulo_%') 
        ])
        adjuntos.unlink()

        # Eliminamos el registro de certificación antiguo si existe
        if self.survey_user_input_id:
            try:
                self.survey_user_input_id.sudo().unlink()
            except Exception:
                 pass # Si no se puede borrar (ej. integridad), lo desvinculamos al escribir False abajo

        # Reseteamos estado para que el CRON lo vuelva a coger
        self.write({
            'titulo_emitido': False,
            'estado_nota': 'pendiente_certificar',
            'fecha_emision_titulo': False
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Regeneración Solicitada',
                'message': 'El título se ha vuelto a encolar. Estará disponible en unos minutos.',
                'type': 'success',
            }
        }

    def action_open_gradebook_form(self):
        """ Abre la vista formulario de esta inscripción específica (usado en botones) """
        self.ensure_one()
        # ASEGURAR INTEGRIDAD: Antes de abrir, generamos/reparamos los registros de evaluación
        self._ensure_evaluacion_records()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Evaluación de Asignatura', # Título explícito
            'res_model': 'slide.channel.partner',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('elearning_universidad.view_slide_channel_partner_form_gradebook').id,
            'target': 'current', # 'current' mantiene las migas de pan
            'context': {'create': False, 'edit': True},
        }

    def _ensure_evaluacion_records(self):
        """ Genera o repara registros de slide.slide.partner para todos los contenidos evaluables """
        SlideSlidePartner = self.env['slide.slide.partner'].sudo()
        Slide = self.env['slide.slide'].sudo()
        
        for record in self:
            # 1. Obtener todos los contenidos RELEVANTES del curso (Evaluables O Tipos especiales)
            # El usuario quiere ver Entregables/Exámenes en la lista aunque no cuenten para nota.
            evaluable_slides = Slide.search([
                ('channel_id', '=', record.channel_id.id),
                ('is_published', '=', True),
                '|', ('es_evaluable', '=', True), ('slide_category', 'in', ['exam', 'delivery', 'certification', 'sub_course'])
            ])
            
            for slide in evaluable_slides:
                # 2. Buscar si ya existe un registro de progreso para este usuario y slide
                progress = SlideSlidePartner.search([
                    ('slide_id', '=', slide.id),
                    ('partner_id', '=', record.partner_id.id)
                ], limit=1)
                
                if progress:
                    # CASO A: Existe pero no está enlazado a nuestra inscripción (channel_partner_id perdidos)
                    if not progress.channel_partner_id:
                        progress.channel_partner_id = record.id
                else:
                    # CASO B: No existe (el alumno no ha entrado aún). Creamos placeholder.
                    SlideSlidePartner.create({
                        'slide_id': slide.id,
                        'partner_id': record.partner_id.id,
                        'channel_id': record.channel_id.id,
                        'channel_partner_id': record.id,
                        'estado_evaluacion': 'pendiente_presentar',
                        # Importante: No marcar como completado ni visitado
                    })
