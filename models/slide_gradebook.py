from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SlideSlidePartner(models.Model):
    _inherit = 'slide.slide.partner'

    channel_partner_id = fields.Many2one(
        'slide.channel.partner', 
        string='Inscripción en Curso',
        compute='_compute_channel_partner_id',
        store=True,
        ondelete='cascade'
    )

    estado_evaluacion = fields.Selection([
        ('pendiente_presentar', 'Pendiente de Presentar'),
        ('pendiente_revision', 'Pendiente de Revisión'),
        ('evaluado', 'Evaluado y Cerrado')
    ], string='Estado de Evaluación', default='pendiente_presentar', required=True)

    nota_evaluacion = fields.Float(string='Nota', default=0.0)
    
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
                            vals['nota_evaluacion'] = (user_input.scoring_percentage / 100.0) * 10
                            vals['estado_evaluacion'] = 'evaluado' # AUTOMÁTICO
                            vals['fecha_entrega'] = fields.Datetime.now()
 
                    elif record.slide_id.slide_category == 'certification' and record.slide_id.survey_id:
                        user_input = self.env['survey.user_input'].search([
                            ('survey_id', '=', record.slide_id.survey_id.id),
                            ('partner_id', '=', record.partner_id.id),
                            ('scoring_success', '=', True)
                        ], limit=1, order='create_date desc')
                        if user_input:
                            vals['nota_evaluacion'] = (user_input.scoring_percentage / 100.0) * 10
                            vals['estado_evaluacion'] = 'evaluado' # AUTOMÁTICO
                            vals['fecha_entrega'] = fields.Datetime.now()
        
        # Si se sube un archivo, pasamos a Pendiente de Revisión
        if 'archivo_entrega' in vals and vals.get('archivo_entrega'):
            vals['estado_evaluacion'] = 'pendiente_revision'
            vals['fecha_entrega'] = fields.Datetime.now()
 
        return super().write(vals)

class SlideChannelPartner(models.Model):
    _inherit = 'slide.channel.partner'

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
        aggregator='avg'
    )
    
    estado_nota = fields.Selection([
        ('pendiente_revision', 'En Curso / Pendiente de Revisión'),
        ('evaluado', 'Evaluado y Confirmado'),
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
        domain=['|', ('slide_id.es_evaluable', '=', True), ('slide_id.slide_category', 'in', ['exam', 'delivery', 'certification', 'sub_course'])]
    )

    # --- Jerarquía y Navegación (Master -> Asignaturas) ---
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
        string='Asignaturas dadas por este alumno en este Master'
    )

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
                    ('channel_id.tipo_curso', '=', 'asignatura')
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
        'channel_id.asignatura_ids.duracion_horas'
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
                record.nota_final = sum(evals.mapped('nota_evaluacion')) / len(evals)
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
             asigs = master.asignatura_ids
             # Filter asignaturas with duration > 0 to avoid division by zero issues in weights (though logical check handles total)
             total_horas = sum(asigs.mapped('duracion_horas'))
             master_data_cache[master.id] = {
                 'asignaturas': asigs,
                 'total_horas': curr_total_horas if (curr_total_horas := total_horas) > 0 else 0
             }

        # Cálculo Final en Memoria
        for record in masters_records:
            m_data = master_data_cache.get(record.channel_id.id)
            
            # Recalculamos total_horas dinámicamente por alumno si fuera necesario (aquí es global del master)
            # Pero si el total de horas es 0, hacemos media aritmética simple.
            total_horas_master = m_data['total_horas'] if m_data else 0
            asignaturas = m_data['asignaturas'] if m_data else []
            
            if not asignaturas:
                 record.nota_final = 0.0
                 continue

            nota_acumulada = 0.0
            
            if total_horas_master > 0:
                # Media Ponderada por Horas
                for asig in asignaturas:
                    nota_asig = scores_map.get((record.partner_id.id, asig.id), 0.0)
                    peso = asig.duracion_horas / total_horas_master
                    nota_acumulada += nota_asig * peso
            else:
                # Media Aritmética Simple (Fallback si no hay horas definidas)
                count = len(asignaturas)
                for asig in asignaturas:
                    nota_asig = scores_map.get((record.partner_id.id, asig.id), 0.0)
                    nota_acumulada += nota_asig
                nota_acumulada = nota_acumulada / count if count > 0 else 0.0
            
            record.nota_final = nota_acumulada

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
            
            # Si el curso emite título y el alumno ha aprobado, pasamos a pendiente de certificar
            if record.channel_id.tiene_titulo and record.nota_final >= 5.0 and not record.titulo_emitido:
                record.estado_nota = 'pendiente_certificar'

    def action_issue_university_degree(self):
        """ Emisión manual de títulos universitarios """
        self.ensure_one()
        if self.estado_nota != 'evaluado':
            raise ValidationError("No se puede emitir un título si el acta no está en estado 'Evaluado'.")
        
        if self.nota_final < 5.0:
            raise ValidationError("El alumno no ha superado satisfactoriamente el curso (Nota < 5.0).")
            
        # Aquí iría la lógica de generación de PDF que recuperaremos más adelante
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Título Generado',
                'message': f'El título para {self.partner_id.name} ha sido generado correctamente.',
                'type': 'success',
            }
        }

    @api.model
    def _cron_emitir_titulos_pendientes(self):
        """ CRON para emitir títulos de alumnos aptos de forma asíncrona """
        inscripciones = self.search([
            ('estado_nota', '=', 'pendiente_certificar'),
            ('titulo_emitido', '=', False)
        ], limit=50) # Procesamos en bloques para evitar timeouts
        
        for inscripcion in inscripciones:
            try:
                # 1. Ejecutar emisión (delegamos en el método manual para reutilizar lógica)
                inscripcion.sudo().action_issue_university_degree()
                
                # 2. Marcar como certificado y registrar fecha
                inscripcion.sudo().write({
                    'estado_nota': 'certificado',
                    'titulo_emitido': True,
                    'fecha_emision_titulo': fields.Datetime.now()
                })
            except Exception as e:
                # Loguear error pero continuar con el siguiente
                continue
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
            'target': 'current', # Forzar navegación en la ventana actual
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
