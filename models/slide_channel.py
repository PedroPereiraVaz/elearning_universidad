from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SlideChannel(models.Model):
    _inherit = 'slide.channel'

    # --- Configuración de Academia ---
    academy_type = fields.Selection([
        ('course', 'Asignatura'),
        ('master', 'Curso')
    ], string='Tipo Académico', default='course', required=True, 
       help="El Curso actúa como un contenedor de Asignaturas.")
    
    # Optimization: One2many to track where this course is used as a subject
    containing_master_slide_ids = fields.One2many('slide.slide', 'sub_channel_id', string="Linked in Masters", readonly=True)
    
    is_subject = fields.Boolean("Es una Asignatura", compute='_compute_is_subject', store=True,
                                help="Técnicamente un curso que pertenece a un Master.")

    upload_size_limit = fields.Integer("Límite de Subida (MB)", default=10, 
                                     help="Tamaño máximo de archivo para entregables en MB (0 para ilimitado).")

    # --- Roles (Unified) ---
    # We use native 'user_id' for 'Director Académico'
    # 'academy_director_id' is kept for backward compatibility or transition but will be synced/hidden
    additional_teacher_ids = fields.Many2many('res.users', string='Profesores',
                                              help="Profesores que pueden calificar entregables y ver el progreso de los estudiantes.")

    # --- Certificación y Lógica ---
    certification_validation = fields.Selection([
        ('auto', 'Automática'),
        ('manual_approval', 'Aprobación Manual Requerida')
    ], string='Proceso de Certificación', default='auto')
    
    @api.model
    def _get_certification_layouts(self):
        return self.env['survey.survey']._fields['certification_report_layout'].selection

    certification_report_layout = fields.Selection(selection='_get_certification_layouts', 
                                                   string='Plantilla del Título', default='modern_gold',
                                                   help="Diseño a utilizar en el diploma generado.")

    # --- Campos Estadísticos (Requeridos por website_slides) ---
    nbr_sub_course = fields.Integer("Número de Asignaturas", compute='_compute_slides_statistics', store=True)
    nbr_delivery = fields.Integer("Número de Entregables", compute='_compute_slides_statistics', store=True)
    
    total_weight = fields.Float("Peso Total (%)", compute='_compute_total_weight')
    
    master_channel_id = fields.Many2one('slide.channel', string="Curso Maestro", 
                                       compute='_compute_master_channel_id', store=False, compute_sudo=True)

    @api.depends('containing_master_slide_ids.channel_id')
    def _compute_master_channel_id(self):
        for record in self:
            if record.containing_master_slide_ids:
                record.master_channel_id = record.containing_master_slide_ids[0].channel_id
            else:
                record.master_channel_id = False
    
    # --- Field Overrides for Teacher Access ---
    # We override these fields to allow Academy Teachers to view attendee data without being full eLearning Officers
    slide_partner_ids = fields.One2many(groups='website_slides.group_website_slides_officer,elearning_academy.group_academy_teacher')
    channel_partner_ids = fields.One2many(groups='website_slides.group_website_slides_officer,elearning_academy.group_academy_teacher')
    channel_partner_all_ids = fields.One2many(groups='website_slides.group_website_slides_officer,elearning_academy.group_academy_teacher')

    # --- Pricing & Product Automation ---
    price_courses = fields.Float(string="Precio del Curso", digits='Product Price',
                               help="Establecer precio para crear/actualizar automáticamente el producto asociado.")

    @api.depends('slide_ids.point_weight', 'slide_ids.is_evaluable')
    def _compute_total_weight(self):
        for record in self:
            slides = record.slide_ids.filtered(lambda s: s.is_evaluable)
            record.total_weight = sum(slides.mapped('point_weight'))

    @api.depends('upload_group_ids', 'user_id', 'additional_teacher_ids')
    @api.depends_context('uid')
    def _compute_can_upload(self):
        """ Include additional_teacher_ids in upload rights """
        for record in self:
            if record.user_id == self.env.user or self.env.user in record.additional_teacher_ids:
                record.can_upload = True
            elif record.upload_group_ids:
                record.can_upload = bool(record.upload_group_ids & self.env.user.groups_id)
            else:
                record.can_upload = self.env.user.has_group('website_slides.group_website_slides_manager')

    @api.depends('channel_type', 'user_id', 'can_upload', 'additional_teacher_ids')
    @api.depends_context('uid')
    def _compute_can_publish(self):
        """ Include additional_teacher_ids in publishing rights """
        for record in self:
            if not record.can_upload:
                record.can_publish = False
            elif record.user_id == self.env.user or self.env.user in record.additional_teacher_ids:
                record.can_publish = True
            else:
                record.can_publish = self.env.user.has_group('website_slides.group_website_slides_manager')

    def _sync_course_product(self):
        """ Helper to Create or Update the associated Product based on Course settings """
        Product = self.env['product.product']
        for channel in self:
            if channel.enroll == 'payment' and channel.price_courses > 0:
                # Prepare values
                product_vals = {
                    'name': channel.name,
                    'list_price': channel.price_courses,
                    'type': 'service',
                    'service_tracking': 'course',
                    'invoice_policy': 'order',
                    'is_published': True,
                }
                
                if channel.product_id:
                    # Update Existing Product (Price & Name)
                    channel.product_id.write(product_vals)
                else:
                    # Create New Product
                    # Try to set a safe category (Generic 'All' or 'Saleable')
                    category = self.env.ref('product.product_category_all', raise_if_not_found=False)
                    if category:
                        product_vals['categ_id'] = category.id
                    
                    product = Product.create(product_vals)
                    channel.product_id = product.id

    @api.model_create_multi
    def create(self, vals_list):
        # Default academy_type handling
        for vals in vals_list:
            if 'academy_type' not in vals:
                # If created from sub-menu, context might have default
                pass
        
        channels = super().create(vals_list)
        for channel in channels:
            channel._sync_course_product()
        return channels

    def write(self, vals):
        # Restrict changing academy_type after creation
        if 'academy_type' in vals:
            for record in self:
                if record.academy_type != vals['academy_type']:
                    raise ValidationError(_("No se puede cambiar el tipo académico una vez creado el curso."))

        res = super().write(vals)

        # Sync if relevant fields changed
        if any(f in vals for f in ['enroll', 'price_courses', 'name']):
            self._sync_course_product()
        return res

    # --- Lógica Computada ---
    @api.depends('containing_master_slide_ids')
    def _compute_is_subject(self):
        # Optimizado: store=True dependiente de relación inversa
        for record in self:
            record.is_subject = bool(record.containing_master_slide_ids)

    @api.onchange('academy_type')
    def _onchange_academy_type(self):
        if self.academy_type == 'master':
            self.certification_validation = 'manual_approval'

    # --- Integridad de Pesos e Inserción ---
    @api.constrains('is_published')
    def _check_academy_weights(self):
        for record in self:
            if record.is_published:
                slides = record.slide_ids.filtered(lambda s: s.is_evaluable)
                if slides:
                    total_weight = sum(slides.mapped('point_weight'))
                    if abs(total_weight - 100.0) > 0.01:
                        raise ValidationError(_("No se puede publicar el curso '%s' porque la suma de pesos de sus contenidos evaluables es %s%% (debe ser 100%%)." % (record.name, total_weight)))

    def action_issue_degrees(self):
        """ 
        Emite títulos (Certificados) usando el motor de encuestas de Odoo.
        Crea/Actualiza una Encuesta 'Shadow' para este curso y genera respuestas 'aprobadas'.
        """
        self.ensure_one()
        if not self.certification_report_layout:
             raise ValidationError("Seleccione una Plantilla de Título antes de emitir.")

        # 1. Obtener estudiantes aprobados
        channel_partners = self.env['slide.channel.partner'].search([
            ('channel_id', '=', self.id),
            ('final_grade', '>=', 5.0) 
        ])
        
        if not channel_partners:
             return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin Aprobados',
                    'message': 'No hay estudiantes aprobados pendientes de título.',
                    'type': 'warning',
                }
            }
            
        # 2. Buscar o Crear la 'Encuesta de Certificación' vinculada a este curso
        survey_title = self.name
        
        survey = self.env['survey.survey'].search([
            ('title', '=', survey_title),
            ('certification', '=', True)
        ], limit=1)
        
        if not survey:
            survey = self.env['survey.survey'].create({
                'title': survey_title,
                'certification': True,
                'scoring_type': 'scoring_without_answers', # Required by Odoo constraint if certification=True
                'certification_report_layout': self.certification_report_layout
            })
        else:
            # Actualizamos el layout por si cambió
            survey.write({'certification_report_layout': self.certification_report_layout})

        # 3. Asegurar estructura mínima del Survey (Necesario para reportes)
        if not survey.question_ids:
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': 'Certificación Académica',
                'question_type': 'text_box', # Tipo simple que no afecta scoring
                'sequence': 1,
            })
            
        # 4. Asegurar que existe un Slide de tipo certificación para que aparezca en el portal
        # Esto vincula el certificado al curso de forma estándar
        cert_slide = self.env['slide.slide'].search([
            ('channel_id', '=', self.id),
            ('slide_category', '=', 'certification'),
            ('survey_id', '=', survey.id)
        ], limit=1)
        
        if not cert_slide:
            cert_slide = self.env['slide.slide'].create({
                'name': f"Certificado: {self.name}",
                'channel_id': self.id,
                'slide_category': 'certification',
                'slide_type': 'certification',
                'survey_id': survey.id,
                'is_published': False, # Oculto para no confundir, pero funcional
                'completion_time': 0,
            })

        # 5. Generar User Inputs (Certificaciones) y actualizar Slide Partner
        user_input_ids = []
        for cp in channel_partners:
            partner = cp.partner_id
            
            # Calcular porcentaje basado en nota final (0-10 -> 0-100)
            score_pct = max(min(cp.final_grade * 10, 100.0), 0.0)
            
            # Verificar si ya existe una certificación exitosa reciente
            existing = self.env['survey.user_input'].search([
                ('survey_id', '=', survey.id),
                ('partner_id', '=', partner.id),
                ('scoring_success', '=', True)
            ], limit=1)
            
            target_input = existing
            
            if existing:
                # Si existe, actualizamos metadata básica
                existing.write({
                    'slide_id': cert_slide.id,
                    'state': 'done'
                })
                user_input_ids.append(existing.id)
            else:
                target_input = self.env['survey.user_input'].create({
                    'survey_id': survey.id,
                    'partner_id': partner.id,
                    'email': partner.email,
                    'state': 'done',
                    'scoring_success': True, # Será sobreescrito por compute, fix abajo
                    'scoring_percentage': score_pct, # Será sobreescrito por compute, fix abajo
                    'slide_id': cert_slide.id
                })
                user_input_ids.append(target_input.id)
            
            # --- BYPASS DE SEGURIDAD/LÓGICA: Persistencia de Nota ---
            # El módulo 'survey' recalcula 'scoring_percentage' a 0 si no hay respuestas ('user_input_lines').
            # Como estamos emitiendo certificaciones basadas en la nota académica (Gradebook) y no en un cuestionario,
            # DEBEMOS inyectar el puntaje directamente en la DB para evitar que el ORM lo resetee.
            # Esta es la única forma de "otorgar" un certificado survey sin "hacer" el survey.
            if target_input:
                self.env.cr.execute("""
                    UPDATE survey_user_input 
                    SET scoring_percentage = %s, scoring_success = true 
                    WHERE id = %s
                """, (score_pct, target_input.id))
                target_input.invalidate_recordset(['scoring_percentage', 'scoring_success'])

            # 6. Marcar el Slide como completado para el alumno
            # Esto hace que aparezca en los reportes de estudiantes certificados
            slide_partner = self.env['slide.slide.partner'].search([
                ('slide_id', '=', cert_slide.id),
                ('partner_id', '=', partner.id)
            ], limit=1)
            
            if not slide_partner:
                slide_partner = self.env['slide.slide.partner'].create({
                    'slide_id': cert_slide.id,
                    'channel_id': self.id,
                    'partner_id': partner.id
                })
            
            if not slide_partner.completed:
                slide_partner.write({
                    'completed': True, 
                    'survey_scoring_success': True
                })
        
        # 6. Imprimir Reporte
        return self.env.ref('survey.certification_report').report_action(user_input_ids)

    def action_add_subject(self):
        self.ensure_one()
        return {
            'name': 'Agregar Asignatura',
            'type': 'ir.actions.act_window',
            'res_model': 'slide.slide',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_channel_id': self.id,
                'default_slide_type': 'sub_course',
                'default_slide_category': 'sub_course',
                'default_is_published': True, # Opcional
            }
        }

    def _action_add_members(self, target_partners, **kwargs):
        """ Override to auto-enroll students in sub-courses (Subject) when enrolling in Master """
        res = super()._action_add_members(target_partners, **kwargs)
        for channel in self:
            # 1. Proactively create slide.slide.partner records for all evaluable content
            # This ensures they appear in the gradebook even before the student visits them
            evaluable_slides = channel.slide_ids.filtered(lambda s: s.is_evaluable)
            if evaluable_slides:
                for partner in target_partners:
                    # Use SUDO to bypass write/create permissions during enrollment flow
                    SlidePartner = self.env['slide.slide.partner'].sudo()
                    for slide in evaluable_slides:
                        existing = SlidePartner.search([
                            ('slide_id', '=', slide.id),
                            ('partner_id', '=', partner.id)
                        ], limit=1)
                        if not existing:
                            SlidePartner.create({
                                'slide_id': slide.id,
                                'partner_id': partner.id,
                                'channel_id': channel.id,
                            })

            # 2. Propagate membership to sub-courses (Subjects)
            if channel.academy_type == 'master':
                # Find all sub-courses
                sub_course_slides = channel.slide_ids.filtered(lambda s: s.slide_category == 'sub_course' and s.sub_channel_id)
                sub_channels = sub_course_slides.mapped('sub_channel_id')
                # Recursively enroll in sub-channels using SUDO to bypass permissions
                if sub_channels:
                    sub_channels.sudo()._action_add_members(target_partners, **kwargs)
        return res

    def _remove_membership(self, partner_ids):
        """ Propagate unenrollment to sub-courses """
        res = super()._remove_membership(partner_ids)
        for channel in self:
            if channel.academy_type == 'master':
                sub_course_slides = channel.slide_ids.filtered(lambda s: s.slide_category == 'sub_course' and s.sub_channel_id)
                sub_channels = sub_course_slides.mapped('sub_channel_id')
                if sub_channels:
                    sub_channels.sudo()._remove_membership(partner_ids)
        return res

class SlideChannelPartner(models.Model):
    _inherit = 'slide.channel.partner'

    final_grade = fields.Float("Calificación Final (0-10)", compute='_compute_final_grade', store=True, readonly=False, aggregator="avg")
    is_manual_grade = fields.Boolean("Calificación Manual", default=False)
    
    # Link to evaluateable content progress (Only Show Evaluable)
    # We use the inverse field we just created in slide.slide.partner
    slide_partner_ids = fields.One2many('slide.slide.partner', 'channel_partner_id', string="Entregas del Estudiante",
                                        domain=[('slide_id.is_evaluable', '=', True)])

    @api.depends('slide_partner_ids.teacher_grade', 'slide_partner_ids.slide_id.point_weight', 'is_manual_grade')
    def _compute_final_grade(self):
        for record in self:
            if record.is_manual_grade:
                continue

            total_score = 0.0
            evaluable_partners = record.slide_partner_ids.filtered(lambda s: s.slide_id.is_evaluable)
            
            for sp in evaluable_partners:
                weight = sp.slide_id.point_weight
                grade = sp.teacher_grade
                if weight > 0:
                    total_score += grade * (weight / 100.0)
            
            record.final_grade = min(max(total_score, 0.0), 10.0)

    @api.constrains('final_grade')
    def _check_final_grade(self):
        for record in self:
            if record.final_grade < 0.0 or record.final_grade > 10.0:
                raise ValidationError(_("La Calificación Final debe estar entre 0 y 10."))

    def write(self, vals):
        res = super().write(vals)
        return res

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        """
        Custom search to filter gradebooks for Teachers:
        ONLY applied when the context 'academy_boletin_filter' is True (List Views).
        1. If they teach a Master, show the Master gradebook (all subjects hidden as they are inside).
        2. If they ONLY teach a Subject (not its parent Master), show the Subject gradebook.
        3. Directors see everything.
        """
        user = self.env.user
        if self._context.get('academy_boletin_filter') and \
           user.has_group('elearning_academy.group_academy_teacher') and \
           not user.has_group('elearning_academy.group_academy_director'):
            # 1. Channels where I am explicitly a teacher or director (owner)
            direct_me = self.env['slide.channel'].search([
                '|', ('user_id', '=', user.id), ('additional_teacher_ids', 'in', user.id)
            ])
            
            # 2. Subjects I can see because I teach their parent Master
            indirect_me = self.env['slide.channel'].search([
                '|', ('containing_master_slide_ids.channel_id.user_id', '=', user.id), 
                     ('containing_master_slide_ids.channel_id.additional_teacher_ids', 'in', user.id)
            ])
            
            all_visible_channels = direct_me | indirect_me
            
            # 3. Filter for the top-level list (Boletines)
            # - We always show Masters where I'm a teacher.
            # - We show a Subject ONLY if I don't teach ANY of its parent Masters.
            master_ids_i_teach = direct_me.filtered(lambda c: c.academy_type == 'master').ids
            
            final_ids = []
            for channel in all_visible_channels:
                if channel.academy_type == 'master':
                    if channel.id in direct_me.ids:
                        final_ids.append(channel.id)
                else:
                    # It's a Subject/Course (academy_type='course')
                    # Find all Masters this Subject belongs to
                    parent_masters = channel.containing_master_slide_ids.mapped('channel_id')
                    
                    # Logic: If I am a teacher of ANY parent master, I don't show the subject individually
                    # because it's already accessible inside the master's evaluation view.
                    is_nested_in_my_masters = any(pm.id in master_ids_i_teach for pm in parent_masters)
                    
                    if not is_nested_in_my_masters:
                        # Case: I ONLY teach this subject, or I teach it but not its master
                        final_ids.append(channel.id)
            
            # Inject filtered IDs into the domain
            domain = [('channel_id', 'in', final_ids)] + domain
            
        return super().search(domain, offset=offset, limit=limit, order=order)
