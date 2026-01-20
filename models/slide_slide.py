from odoo.exceptions import ValidationError
from odoo.http import request
from odoo import models, fields, api, _
from markupsafe import Markup
from werkzeug import urls

class Slide(models.Model):
    _inherit = 'slide.slide'

    slide_category = fields.Selection(selection_add=[
        ('sub_course', 'Asignatura'),
        ('delivery', 'Entregable')
    ], ondelete={'sub_course': 'cascade', 'delivery': 'cascade'})

    channel_academy_type = fields.Selection(related='channel_id.academy_type', string="Tipo de Academia del Canal")

    slide_type = fields.Selection(selection_add=[
        ('delivery', 'Entregable (Calificación Manual)'),
        ('sub_course', 'Asignatura (Curso)')
    ], ondelete={'delivery': 'cascade', 'sub_course': 'cascade'})

    delivery_max_score = fields.Float("Puntuación Máxima", default=10.0, help="Puntuación máxima para este entregable.")
    
    # --- Ponderación y Enlace ---
    point_weight = fields.Float("Peso", default=0.0, help="Peso de este contenido en la nota final del curso (0-100).")
    
    sub_channel_id = fields.Many2one('slide.channel', string="Asignatura", 
                                     domain=[('academy_type', '=', 'course'), ('is_subject', '=', False)],
                                     help="El curso que actúa como asignatura.")

    # Related fields to manage the Subject directly from the Master content form
    sub_channel_user_id = fields.Many2one('res.users', related='sub_channel_id.user_id', string="Director de Asignatura", readonly=False)
    sub_channel_additional_teacher_ids = fields.Many2many('res.users', related='sub_channel_id.additional_teacher_ids', string="Profesores de Asignatura", readonly=False)

    @api.onchange('sub_channel_id')
    def _onchange_sub_channel_id(self):
        if self.sub_channel_id:
            self.name = self.sub_channel_id.name
    
    # Manual toggle for evaluation
    is_evaluable = fields.Boolean("Es Evaluable", default=False, help="Si se marca, este contenido contará para la nota final.")

    @api.constrains('channel_id', 'sub_channel_id', 'slide_category')
    def _check_nesting_levels(self):
        for record in self:
            # 1. Master can contain Subjects, but not other Masters
            if record.channel_id.academy_type == 'master':
                if record.slide_category == 'sub_course' and record.sub_channel_id.academy_type != 'course':
                    raise ValidationError("Un curso de tipo 'Curso' solo puede contener 'Asignaturas'.")
            
            # 2. Subject cannot contain other Subjects or Masters
            if record.channel_id.academy_type == 'course':
                if record.slide_category == 'sub_course':
                    raise ValidationError("Una 'Asignatura' no puede contener otras asignaturas o cursos.")

            # 3. Subject Uniqueness: A subject course can only be linked to ONE parent course (Master)
            if record.slide_category == 'sub_course' and record.sub_channel_id:
                if record.channel_academy_type != 'master':
                    raise ValidationError("Solo se pueden añadir Asignaturas a cursos de tipo 'Curso' (Master).")
                
                already_linked = self.search_count([
                    ('id', '!=', record.id),
                    ('slide_category', '=', 'sub_course'),
                    ('sub_channel_id', '=', record.sub_channel_id.id)
                ])
                if already_linked > 0:
                    raise ValidationError(f"La asignatura '{record.sub_channel_id.name}' ya está asignada a otro curso.")



    # --- Scheduled Publishing ---
    scheduled_publish_date = fields.Datetime("Fecha de Publicación Programada")
    
    @api.model
    def _cron_publish_scheduled_slides(self):
        """ Cron job to publish slides with reached scheduled date """
        slides_to_publish = self.search([
            ('is_published', '=', False),
            ('scheduled_publish_date', '!=', False),
            ('scheduled_publish_date', '<=', fields.Datetime.now())
        ])
        if slides_to_publish:
            slides_to_publish.write({
                'is_published': True,
                'date_published': fields.Datetime.now(),
                'scheduled_publish_date': False # Clear after publishing
            })
            # _logger.info(f"Published {len(slides_to_publish)} scheduled slides.")

    # --- Campos Estadísticos (Requeridos por website_slides para Secciones) ---
    nbr_sub_course = fields.Integer("Número de Asignaturas", compute='_compute_slides_statistics', store=True)
    nbr_delivery = fields.Integer("Número de Entregables", compute='_compute_slides_statistics', store=True)
    nbr_degree = fields.Integer("Número de Títulos", compute='_compute_slides_statistics', store=True)



    @api.onchange('slide_category')
    def _onchange_slide_category_evaluable(self):
        # Default to evaluable for graded types
        if self.slide_category in ['quiz', 'delivery', 'sub_course', 'certification']:
            self.is_evaluable = True
        else:
            self.is_evaluable = False

    @api.depends('slide_category')
    def _compute_slide_type(self):
        super()._compute_slide_type()
        for slide in self:
            if slide.slide_category == 'sub_course':
                slide.slide_type = 'sub_course'
            elif slide.slide_category == 'delivery':
                slide.slide_type = 'delivery'








    def _propagate_subject_status(self, vals):
        """ Enroll students and publish subject courses if the master content is published """
        for slide in self:
            if slide.slide_category != 'sub_course' or not slide.sub_channel_id:
                continue

            # 1. Propagation of Membership (Inherited from Master)
            master_channel = slide.channel_id
            if master_channel.academy_type == 'master':
                partners = master_channel.channel_partner_ids.mapped('partner_id')
                if partners:
                    slide.sub_channel_id.sudo()._action_add_members(partners)
            
            # 2. Propagation of Publication Status
            # If the slide IS published (already or in this write/create), publish the sub-course
            if slide.is_published:
                slide.sub_channel_id.sudo().write({'is_published': True})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('slide_category') == 'sub_course':
                vals['is_evaluable'] = True
        slides = super().create(vals_list)
        slides._propagate_subject_status(vals_list)
        return slides

    def write(self, vals):
        if vals.get('slide_category') == 'sub_course':
            vals['is_evaluable'] = True
            
        res = super().write(vals)
        # Trigger if publishing OR changing relationship
        if any(f in vals for f in ['is_published', 'sub_channel_id', 'slide_category', 'channel_id']):
            self._propagate_subject_status(vals)
        return res

    def _action_mark_completed(self):
        """ 
        Override to prevent marking deliverables as completed just by visiting them.
        They must be marked as completed ONLY when a file is uploaded.
        """
        # Filter out deliverables from automatic completion
        auto_completable = self.filtered(lambda s: s.slide_category != 'delivery')
        if auto_completable:
            return super(Slide, auto_completable)._action_mark_completed()
        return False

    @api.depends('slide_category')
    def _compute_embed_code(self):
        super()._compute_embed_code()
        request_base_url = request.httprequest.url_root if request else False
        for slide in self:
            if slide.slide_category == 'delivery':
                base_url = request_base_url or slide.get_base_url()
                if base_url[-1] == '/':
                    base_url = base_url[:-1]
                
                slide_url = base_url + self.env['ir.http']._url_for('/slides/embed/%s?page=1' % slide.id)
                slide_url_external = base_url + self.env['ir.http']._url_for('/slides/embed_external/%s?page=1' % slide.id)
                base_embed_code = Markup('<iframe src="%s" class="o_wslides_iframe_viewer" allowFullScreen="true" height="%s" width="%s" frameborder="0" aria-label="%s"></iframe>')
                iframe_aria_label = _('Embed code')
                
                slide.embed_code = base_embed_code % (slide_url, 315, 420, iframe_aria_label)
                slide.embed_code_external = base_embed_code % (slide_url_external, 315, 420, iframe_aria_label)

    def _compute_website_url(self):
        super()._compute_website_url()
        for slide in self:
            if slide.slide_category == 'sub_course' and slide.sub_channel_id:
                # Redirect to first content of the sub-course to simulate seamless flow
                first_slide = self.env['slide.slide'].search([
                    ('channel_id', '=', slide.sub_channel_id.id),
                    ('is_published', '=', True),
                    ('is_category', '=', False)
                ], order='sequence, id', limit=1)
                
                if first_slide:
                    slide.website_url = first_slide.website_url
                else:
                    slide.website_url = slide.sub_channel_id.website_url





class SlidePartner(models.Model):
    _inherit = 'slide.slide.partner'

    delivery_file = fields.Binary("Entregable del Estudiante")
    delivery_filename = fields.Char("Nombre del Archivo")
    delivery_date = fields.Datetime("Fecha de Entrega")
    delivery_date = fields.Datetime("Fecha de Entrega")
    
    # Nuevo campo para almacenar calificación manual (Entregables, etc.)
    manual_grade = fields.Float("Calificación Manual (Interna)", default=0.0)
    
    # Campo computado principal que expone la nota correcta según el contexto
    teacher_grade = fields.Float(
        "Calificación del Profesor", 
        compute='_compute_teacher_grade', 
        inverse='_inverse_teacher_grade', 
        store=False, 
        readonly=False
    )
    
    teacher_feedback = fields.Text("Feedback del Profesor")

    @api.constrains('teacher_grade')
    def _check_teacher_grade(self):
        for record in self:
            if record.teacher_grade < 0.0 or record.teacher_grade > 10.0:
                raise ValidationError("La Calificación del Profesor debe estar entre 0 y 10.")
    
    @api.depends('manual_grade', 'slide_category')
    def _compute_teacher_grade(self):
        for record in self:
            if record.slide_category == 'sub_course' and record.slide_id.sub_channel_id:
                # Buscar la inscripción en el curso hijo (Asignatura)
                sub_enrollment = self.env['slide.channel.partner'].search([
                    ('channel_id', '=', record.slide_id.sub_channel_id.id),
                    ('partner_id', '=', record.partner_id.id)
                ], limit=1)
                if sub_enrollment:
                    record.teacher_grade = sub_enrollment.final_grade
                else:
                    record.teacher_grade = 0.0
            else:
                record.teacher_grade = record.manual_grade

    def _inverse_teacher_grade(self):
        for record in self:
            if record.slide_category != 'sub_course':
                record.manual_grade = record.teacher_grade
            # Si es sub_course, ignoramos la escritura o podríamos lanzar error si se intenta editar manualmente
    status = fields.Selection([
        ('pending', 'Pendiente'),
        ('submitted', 'Entregado'),
        ('graded', 'Calificado')
    ], default='pending', string="Estado de Entrega")

    # Eliminamos evaluation_item_id ya que la lógica se mueve aquí
    # evaluation_item_id = fields.Many2one('academy.evaluation.item', string="Item de Evaluación", readonly=True)

    channel_partner_id = fields.Many2one('slide.channel.partner', string="Inscripción del Curso",
                                         compute='_compute_channel_partner_id', store=True)

    slide_category = fields.Selection(related='slide_id.slide_category', string="Categoría de Slide", readonly=True)
    point_weight = fields.Float(related='slide_id.point_weight', string="Peso (%)", readonly=True)

    @api.depends('channel_id', 'partner_id')
    def _compute_channel_partner_id(self):
        for record in self:
            if record.channel_id and record.partner_id:
                record.channel_partner_id = self.env['slide.channel.partner'].search([
                    ('channel_id', '=', record.channel_id.id),
                    ('partner_id', '=', record.partner_id.id)
                ], limit=1)
            else:
                record.channel_partner_id = False

    def write(self, vals):
        res = super().write(vals)
        # Auto-grade logic when marked as completed
        if vals.get('completed'):
            for record in self:
                # 1. Quizzes (If passed, usually means 10)
                if record.slide_category == 'quiz' and record.status != 'graded':
                    record.write({
                        'teacher_grade': 10.0,
                        'status': 'graded'
                    })
                
                # 2. Certifications (Survey)
                elif record.slide_category == 'certification' and record.slide_id.survey_id:
                     user_input = self.env['survey.user_input'].search([
                        ('survey_id', '=', record.slide_id.survey_id.id),
                        ('partner_id', '=', record.partner_id.id),
                        ('scoring_success', '=', True)
                     ], limit=1, order='create_date desc')
                     
                     if user_input:
                         grade = (user_input.scoring_percentage / 100.0) * 10
                         record.write({
                             'teacher_grade': grade,
                             'status': 'graded'
                         })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def action_set_graded(self):
        self.ensure_one()
        self.status = 'graded'

    def action_open_sub_course_grading(self):
        self.ensure_one()
        if self.slide_id.slide_category != 'sub_course' or not self.slide_id.sub_channel_id:
            return
        
        # Determine the target channel (Subject)
        target_channel = self.slide_id.sub_channel_id
        target_partner = self.partner_id
        
        # Find the enrollment record
        # Clear the boletin filter to ensure we can find the nested subject record
        channel_partner = self.env['slide.channel.partner'].with_context(academy_boletin_filter=False).search([
            ('channel_id', '=', target_channel.id),
            ('partner_id', '=', target_partner.id)
        ], limit=1)
        
        if channel_partner:
            return {
                'name': f'Evaluación: {target_channel.name}',
                'type': 'ir.actions.act_window',
                'res_model': 'slide.channel.partner',
                'view_mode': 'form',
                'res_id': channel_partner.id,
                'target': 'current',
            }
