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

    @api.constrains('nota_evaluacion')
    def _check_nota(self):
        for record in self:
            if record.nota_evaluacion < 0 or record.nota_evaluacion > 10:
                raise ValidationError("La nota debe estar entre 0 y 10")

    def accion_confirmar_nota(self):
        """ El profesor confirma que la nota del contenido es definitiva """
        for record in self:
            if not record.slide_id.es_evaluable:
                raise ValidationError("Solo se pueden evaluar contenidos marcados como evaluables.")
            if record.estado_evaluacion == 'pendiente_presentar':
                raise ValidationError("No se puede evaluar un contenido que aún no ha sido presentado.")
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
                            vals['estado_evaluacion'] = 'pendiente_revision'
                            vals['fecha_entrega'] = fields.Datetime.now()

                    elif record.slide_id.slide_category == 'certification' and record.slide_id.survey_id:
                        user_input = self.env['survey.user_input'].search([
                            ('survey_id', '=', record.slide_id.survey_id.id),
                            ('partner_id', '=', record.partner_id.id),
                            ('scoring_success', '=', True)
                        ], limit=1, order='create_date desc')
                        if user_input:
                            vals['nota_evaluacion'] = (user_input.scoring_percentage / 100.0) * 10
                            vals['estado_evaluacion'] = 'pendiente_revision'
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
            
        return super().create(vals_filtrados)

    # --- Notas y Estados ---
    nota_final = fields.Float(
        string='Nota Académica', 
        compute='_compute_nota_academica', 
        store=True, 
        readonly=False,
        aggregator='avg'
    )
    
    estado_nota = fields.Selection([
        ('pendiente_presentar', 'Pendiente de Presentar'),
        ('pendiente_revision', 'Pendiente de Revisión'),
        ('evaluado', 'Evaluado y Confirmado'),
        ('pendiente_certificar', 'Título Pendiente de Emitir'),
        ('certificado', 'Título Emitido')
    ], string='Estado Acta', default='pendiente_presentar', required=True)

    # --- Tracking de Certificación ---
    titulo_emitido = fields.Boolean(string="Título Generado", default=False, readonly=True)
    fecha_emision_titulo = fields.Datetime(string="Fecha de Emisión", readonly=True)
    survey_user_input_id = fields.Many2one('survey.user_input', string="Certificación Vinculada", readonly=True)

    nota_manual = fields.Boolean(
        string='Corrección Manual', 
        default=False,
        help="Si se marca, el profesor puede sobreescribir la nota autocalculada."
    )

    # Relación para acceder a las evaluaciones de contenidos desde el boletín
    evaluaciones_ids = fields.One2many(
        'slide.slide.partner', 
        'channel_partner_id', 
        string='Evaluaciones de Contenido',
        domain=[('slide_id.es_evaluable', '=', True)]
    )

    @api.depends(
        'channel_id.tipo_curso', 
        'nota_manual',
        'evaluaciones_ids.nota_evaluacion', 
        'evaluaciones_ids.estado_evaluacion',
        'channel_id.asignatura_ids.duracion_horas'
    )
    def _compute_nota_academica(self):
        for record in self:
            if record.nota_manual:
                continue

            tipo = record.channel_id.tipo_curso
            
            if tipo in ['asignatura', 'microcredencial']:
                # Promedio simple de contenidos evaluables
                evals = record.evaluaciones_ids
                if evals:
                    record.nota_final = sum(evals.mapped('nota_evaluacion')) / len(evals)
                else:
                    record.nota_final = 0.0
            
            elif tipo == 'master':
                # Ponderación por duración de asignaturas
                asignaturas = record.channel_id.asignatura_ids
                if not asignaturas:
                    record.nota_final = 0.0
                    continue

                total_horas = sum(asignaturas.mapped('duracion_horas'))
                if total_horas <= 0:
                    record.nota_final = 0.0
                    continue

                nota_ponderada = 0.0
                for asig in asignaturas:
                    # Buscamos la inscripción del alumno en esa asignatura
                    inscripcion_asig = self.env['slide.channel.partner'].search([
                        ('channel_id', '=', asig.id),
                        ('partner_id', '=', record.partner_id.id)
                    ], limit=1)
                    
                    if inscripcion_asig:
                        peso = asig.duracion_horas / total_horas
                        nota_ponderada += inscripcion_asig.nota_final * peso
                
                record.nota_final = nota_ponderada

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
