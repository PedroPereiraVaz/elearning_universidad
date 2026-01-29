from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class Slide(models.Model):
    _inherit = 'slide.slide'

    es_evaluable = fields.Boolean(
        string='Contenido Evaluable', 
        default=False, 
        help="Si se marca, este contenido requerirá una calificación manual para cerrar la nota de la asignatura."
    )

    # Enlace a la asignatura si este slide es un puente en un Master
    asignatura_id = fields.Many2one(
        'slide.channel', 
        string='Asignatura Vinculada',
        domain=[('tipo_curso', '=', 'asignatura')]
    )

    canal_tipo_curso = fields.Selection(
        related='channel_id.tipo_curso', 
        string='Tipo de Curso del Canal', 
        readonly=True,
        store=True
    )
    

    fecha_programada = fields.Datetime(
        string='Publicación Programada', 
        help="Fecha en la que el contenido se publicará automáticamente."
    )

    # --- Campos Estadísticos Técnicos ---
    nbr_sub_course = fields.Integer(string='Número de Asignaturas', compute='_compute_slides_statistics', store=True, compute_sudo=True)
    nbr_delivery = fields.Integer(string='Número de Entregables', compute='_compute_slides_statistics', store=True, compute_sudo=True)
    nbr_exam = fields.Integer(string='Número de Exámenes', compute='_compute_slides_statistics', store=True, compute_sudo=True)

    slide_category = fields.Selection(selection_add=[
        ('quiz', 'Self-Assessment Quiz'), # Source in English
        ('sub_course', 'Asignatura'),
        ('delivery', 'Entregable'),
        ('exam', 'Examen')
    ], ondelete={'sub_course': 'cascade', 'delivery': 'cascade', 'exam': 'cascade'})

    slide_type = fields.Selection(selection_add=[
        ('quiz', 'Self-Assessment Quiz'), # Source in English
        ('sub_course', 'Asignatura'),
        ('delivery', 'Entregable'),
        ('exam', 'Examen')
    ], ondelete={'sub_course': 'cascade', 'delivery': 'cascade', 'exam': 'cascade'})



    # --- UI Helpers ---
    #campo relacionado para separar la vista de Exámenes con su propio contexto
    exam_id = fields.Many2one('survey.survey', related='survey_id', readonly=False, string="Examen")

    # --- Integridad de Responsables ---
    allowed_user_ids = fields.Many2many(
        'res.users', 
        compute='_compute_allowed_users', 
        string="Responsables Permitidos"
    )

    @api.depends('channel_id.director_academico_ids', 'channel_id.personal_docente_ids')
    def _compute_allowed_users(self):
        for record in self:
            if record.channel_id:
                record.allowed_user_ids = record.channel_id.director_academico_ids | record.channel_id.personal_docente_ids
            else:
                record.allowed_user_ids = self.env['res.users']

    @api.constrains('user_id', 'channel_id')
    def _check_responsible_is_staff(self):
        for record in self:
            # Si hay un responsable y un curso asignado
            # Excepción: Si es superusuario/root (instalación), saltar check. 
            # (Aunque 'user_id' es el campo de valor).
            if record.user_id and record.channel_id:
                valid_staff = record.channel_id.director_academico_ids | record.channel_id.personal_docente_ids
                if valid_staff and record.user_id not in valid_staff:
                    # Solo validamos si el curso TIENE staff definido. Si está vacío, quizás es pre-configuración.
                    # Pero el requerimiento es estricto: "nadie mas que no este en el curso".
                    # Si no hay staff, nadie debería ser responsable salvo el admin quizas.
                    # Asumimos que valid_staff es la autoridad.
                    raise ValidationError(_(
                        "Error de Integridad: El responsable '%s' no pertenece al Personal Docente ni a Dirección del curso."
                        "\nDebe añadirlo previamente a la configuración del curso."
                    ) % record.user_id.name)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """ 
        Sobrescribe la vista para filtrar dinámicamente los tipos de contenido.
        ESTRATEGIA DE SEPARACIÓN ESTRICTA:
        1. Por defecto: Ocultar 'Asignatura' (sub_course) y 'Certificación'.
        2. Excepción Master: Si el contexto trae 'force_master_content=True', 
           entonces MOSTRAR 'Asignatura' y OCULTAR todo lo demás.
        """
        res = super().get_view(view_id=view_id, view_type=view_type, **options)
        
        # Aplicamos el filtro en FORM, TREE y SEARCH (para mayor seguridad)
        if view_type in ['form', 'tree', 'list', 'search'] and 'fields' in res and 'slide_category' in res['fields']:
            selection = res['fields']['slide_category']['selection']
            force_master = self.env.context.get('force_master_content')

            if force_master:
                # MODO MASTER (Botón "Agregar Asignatura"):
                # Solo permitimos 'Asignatura'
                selection = [opt for opt in selection if opt[0] == 'sub_course']
                # Opcional: Podríamos intentar hacer el campo readonly aquí si fuera necesario, 
                # pero mejor confiamos en el default del botón.
            else:
                # MODO ESTÁNDAR (Lista normal, Botón "Agregar Contenido"):
                # Ocultamos 'Asignatura' y 'Certificación'
                selection = [opt for opt in selection if opt[0] not in ['sub_course', 'certification']]

            res['fields']['slide_category']['selection'] = selection
                
        return res

    def action_open_add_asignatura(self, *args):
        """ 
        Acción llamada desde el botón 'Agregar Asignatura' en la lista de contenidos (slide_ids).
        Se define aquí porque el botón está dentro del control del One2many (slide.slide).
        Recupera el canal padre del contexto 'default_channel_id'.
        """
        channel_id = self.env.context.get('default_channel_id') or self.env.context.get('active_id')
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agregar Asignatura',
            'res_model': 'slide.slide',
            'view_mode': 'form',
            'view_id': self.env.ref('website_slides.view_slide_slide_form_wo_channel_id').id,
            'target': 'new',
            'context': {
                'default_channel_id': channel_id,
                'default_slide_category': 'sub_course',
                'default_is_category': False,
                'force_master_content': True, # Permite que fields_get muestre 'sub_course'
            }
        }

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """
        Definición global de campos. 
        Por defecto ocultamos 'sub_course' y 'certification'.
        Pero si el contexto 'force_master_content' está activo, permitimos 'sub_course'.
        """
        res = super().fields_get(allfields, attributes)
        if 'slide_category' in res and 'selection' in res['slide_category']:
            selection = res['slide_category']['selection']
            
            # Check context for Master override
            force_master = self.env.context.get('force_master_content')
            
            if force_master:
                 # Si forzamos contenido de Master, SOLO permitimos sub_course (y eliminamos el resto si se desea, 
                 # pero aquí lo importante es NO eliminar sub_course si lo vamos a usar).
                 # Para simplificar y no romper nada más, solo eliminamos certification.
                 # La logica de "Solo Asignatura" ya se aplica en get_view para la UI.
                 allowed_remove = ['certification']
            else:
                 # Por defecto ocultamos ambos
                 allowed_remove = ['sub_course', 'certification']

            res['slide_category']['selection'] = [
                option for option in selection if option[0] not in allowed_remove
            ]
        return res

    _sql_constraints = [
        ('asignatura_unique', 'unique(asignatura_id)', 'Esta asignatura ya está vinculada a otro curso Master.'),
    ]

    # --- Restricciones de Contenido para Masters ---
    @api.constrains('channel_id', 'slide_category')
    def _check_master_content(self):
        for record in self:
            if record.channel_id.tipo_curso == 'master':
                # Solo permitimos Secciones (category) y Asignaturas sincronizadas (sub_course)
                # Cualquier otro tipo (video, document, quiz, certification) está prohibido
                if record.is_category: # Es una sección
                    continue
                if record.slide_category == 'sub_course': # Es una asignatura
                    continue
                
                raise ValidationError(_("En un Master solo se pueden agregar 'Secciones' o 'Asignaturas'. No se permite contenido directo."))
            
            # Regla Inversa: No permitir Asignaturas dentro de Asignaturas o Microcredenciales
            if record.channel_id.tipo_curso != 'master' and record.slide_category == 'sub_course':
                raise ValidationError(_("Solo los Masters pueden contener Asignaturas. En una Asignatura/Microcredencial debes agregar contenido real (Vídeos, PDFs, etc)."))

    @api.depends('slide_category')
    def _compute_slide_type(self):
        super()._compute_slide_type()
        for slide in self:
            if slide.slide_category == 'exam':
                slide.slide_type = 'exam'
            if slide.slide_category in ['sub_course', 'delivery']:
                slide.slide_type = slide.slide_category

    @api.depends('slide_type')
    def _compute_slide_icon_class(self):
        for slide in self:
            if slide.slide_type == 'exam':
                slide.slide_icon_class = 'fa-pencil-square-o'
        super(Slide, self.filtered(lambda s: s.slide_type != 'exam'))._compute_slide_icon_class()

    def _generate_certification_url(self):
        """ 
        Generar URL para Exámenes igual que para Certificaciones.
        Replica la lógica de _generate_certification_url de website_slides_survey pero para category='exam'.
        """
        certification_urls = super(Slide, self)._generate_certification_url()
        
        # Procesamos slides tipo 'exam' que tengan un examen vinculado
        for slide in self.filtered(lambda s: s.slide_category == 'exam' and s.survey_id):
            # Misma lógica que el original: User Input existente o nuevo
            if slide.channel_id.is_member:
                user_membership_id_sudo = slide.user_membership_id.sudo()
                if user_membership_id_sudo.user_input_ids:
                    last_user_input = next(user_input for user_input in user_membership_id_sudo.user_input_ids.sorted(
                        lambda user_input: user_input.create_date, reverse=True
                    ))
                    certification_urls[slide.id] = last_user_input.get_start_url()
                else:
                    user_input = slide.survey_id.sudo()._create_answer(
                        partner=self.env.user.partner_id,
                        check_attempts=False,
                        **{
                            'slide_id': slide.id,
                            'slide_partner_id': user_membership_id_sudo.id
                        },
                        invite_token=self.env['survey.user_input']._generate_invite_token()
                    )
                    certification_urls[slide.id] = user_input.get_start_url()
            else:
                user_input = slide.survey_id.sudo()._create_answer(
                    partner=self.env.user.partner_id,
                    check_attempts=False,
                    test_entry=True, **{
                        'slide_id': slide.id
                    }
                )
                certification_urls[slide.id] = user_input.get_start_url()
                
        return certification_urls

    def action_publicar_contenido(self):
        """ Publica inmediatamente el contenido """
        for slide in self:
            slide.write({
                'is_published': True,
                'date_published': fields.Datetime.now(),
                'fecha_programada': False
            })
            slide._propagar_publicacion_asignatura()

    def action_programar_publicacion(self):
        """ Confirma la programación (UX helper, la lógica real es el campo fecha_programada) """
        for slide in self:
            if not slide.fecha_programada:
                raise ValidationError(_("Debe establecer una fecha programada antes de confirmar."))
            if slide.is_published:
                slide.is_published = False

    @api.constrains('fecha_programada')
    def _check_fecha_programada(self):
        for slide in self:
            if slide.fecha_programada and slide.fecha_programada < fields.Datetime.now():
                raise ValidationError(_("La fecha programada no puede ser anterior al momento actual."))

    @api.constrains('es_evaluable', 'slide_category')
    def _check_evaluable_integrity(self):
        """ Aplicar tipos evaluables estrictos """
        ALLOWED = ['certification', 'delivery', 'sub_course', 'exam']
        for slide in self:
            if slide.es_evaluable and slide.slide_category not in ALLOWED:
                raise ValidationError(_("Solo los siguientes contenidos pueden ser evaluables: Examen, Asignatura, Entregable, Certificación.\nEl tipo '%s' no admite evaluación.") % slide.slide_category)

    @api.constrains('slide_category', 'completion_time')
    def _check_completion_time_asignatura(self):
        """ La duración de la asignatura como contenido debe ser mayor a 0 """
        for slide in self:
            if slide.slide_category == 'sub_course' and slide.completion_time <= 0:
                raise ValidationError(_("La duración de la asignatura '%s' debe ser mayor a 0 horas.") % slide.name)

    def _propagar_publicacion_asignatura(self):
        """ Sincroniza el estado de la asignatura vinculada con el slide del Master """
        if self.env.context.get('avoid_recursive_sync'):
            return

        for slide in self.filtered(lambda s: s.asignatura_id):
            if slide.is_published:
                slide.asignatura_id.sudo().with_context(avoid_slide_sync=True, avoid_recursive_sync=True).action_publicar()
            elif slide.fecha_programada:
                slide.asignatura_id.sudo().with_context(avoid_slide_sync=True, avoid_recursive_sync=True).write({
                    'estado_universidad': 'programado',
                    'fecha_programada_publicacion': slide.fecha_programada
                })

    def _asegurar_registros_seguimiento(self):
        """ Crea slide.slide.partner para todos los alumnos del curso si el contenido es evaluable """
        SlidePartner = self.env['slide.slide.partner'].sudo()
        for slide in self.filtered(lambda s: s.es_evaluable and s.channel_id):
            alumnos = slide.channel_id.channel_partner_ids.mapped('partner_id')
            for alumno in alumnos:
                existente = SlidePartner.search([
                    ('slide_id', '=', slide.id),
                    ('partner_id', '=', alumno.id)
                ], limit=1)
                if not existente:
                    SlidePartner.create({
                        'slide_id': slide.id,
                        'partner_id': alumno.id,
                        'channel_id': slide.channel_id.id,
                        'estado_evaluacion': 'pendiente_presentar'
                    })

    @api.onchange('asignatura_id')
    def _onchange_asignatura_id(self):
        """ Copiar título de la asignatura al contenido automáticamente (Sobrescritura forzada) """
        if self.asignatura_id:
            self.name = self.asignatura_id.name

    @api.onchange('exam_id')
    def _onchange_exam_id(self):
        """ Copiar título del examen al contenido automáticamente """
        if self.exam_id:
            self.name = self.exam_id.title

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('channel_id'):
                canal = self.env['slide.channel'].browse(vals['channel_id'])
                if canal.tipo_curso == 'master':
                    if not vals.get('is_category') and not vals.get('asignatura_id'):
                        raise ValidationError("Un 'Master' solo puede contener 'Asignaturas'.")
            
            # Fallback por si la UI no mandó nombre (campo oculto)
            if not vals.get('name') and vals.get('asignatura_id'):
                asignatura = self.env['slide.channel'].browse(vals['asignatura_id'])
                vals['name'] = asignatura.name
            
            # Corrección: Forzar 'es_evaluable' para Asignaturas, Exámenes y Entregables en creación
            if vals.get('slide_category') in ['sub_course', 'delivery', 'exam', 'certification']:
                if 'es_evaluable' not in vals:
                    vals['es_evaluable'] = True
        
        slides = super().create(vals_list)
        
        # FIX CATEGORÍA EXAMEN
        # El módulo website_slides_survey.create fuerza slide_category='certification' 
        # si hay survey_id. Debemos restaurarlo si la intención original era 'exam'.
        # Iteramos sobre los vals_list para ver qué pidió el usuario originalmente.
        for slide, vals in zip(slides, vals_list):
            if vals.get('slide_category') == 'exam' and slide.slide_category != 'exam':
                slide.write({'slide_category': 'exam'})

        slides._asegurar_registros_seguimiento()
        slides._sincronizar_asignatura_master() # Primero vinculamos al Master (para cumplir requisitos)
        slides._propagar_publicacion_asignatura() # Luego intentamos publicar
        return slides

    def write(self, vals):

        res = super().write(vals)
        if 'es_evaluable' in vals and vals.get('es_evaluable'):
            self._asegurar_registros_seguimiento()
        
        if any(k in vals for k in ['is_published', 'fecha_programada', 'asignatura_id']):
            self._propagar_publicacion_asignatura()
        
        if 'asignatura_id' in vals or 'channel_id' in vals:
            self._sincronizar_asignatura_master() # Nuevo
            
        return res

    def unlink(self):
        """ 
        Al eliminar una slide de tipo Sub-Course, debemos liberar la Asignatura
        para que deje de apuntar al Master y pueda ser asignada a otro.
        """
        for slide in self:
            if slide.slide_category == 'sub_course' and slide.asignatura_id:
                # Si estamos borrando el link del Master, liberamos la asignatura
                if slide.channel_id.tipo_curso == 'master' and slide.asignatura_id.master_id == slide.channel_id:
                     # Usamos avoid_slide_sync para evitar que la asignatura intente borrar este slide (que ya se está borrando)
                     # y cause un error de "Registro eliminado".
                    slide.asignatura_id.sudo().with_context(avoid_slide_sync=True).write({'master_id': False})
        
        return super().unlink()

    def _sincronizar_asignatura_master(self):
        """ 
        Bidireccionalidad: Si vinculamos una Asignatura a un Master (creando un slide),
        actualizamos el campo master_id de la Asignatura para que queden casados.
        """
        if self.env.context.get('avoid_recursive_sync'):
            return
            
        for slide in self:
            if slide.slide_category == 'sub_course' and slide.asignatura_id and slide.channel_id.tipo_curso == 'master':
                if slide.asignatura_id.master_id != slide.channel_id:
                    # Contexto para romper bucle infinito (Evitar que el canal intente crear el slide de vuelta)
                    # Y SINCRONIZAMOS DIRECTORES AUTOMÁTICAMENTE
                    vals_sync = {
                        'master_id': slide.channel_id.id,
                        'director_academico_ids': [(6, 0, slide.channel_id.director_academico_ids.ids)]
                    }
                    slide.asignatura_id.sudo().with_context(avoid_slide_sync=True, avoid_recursive_sync=True).write(vals_sync)

    @api.model
    def _cron_publicar_slides_programados(self):
        """ CRON para publicar contenidos cuya fecha programada haya llegado """
        slides = self.search([
            ('is_published', '=', False),
            ('fecha_programada', '!=', False),
            ('fecha_programada', '<=', fields.Datetime.now())
        ])
        for slide in slides:
            # Publicación asíncrona vía CRON
            slide.sudo().write({
                'is_published': True,
                'date_published': fields.Datetime.now(),
                'fecha_programada': False # Limpiamos para no re-procesar
            })

    @api.depends('asignatura_id')
    def _compute_website_url(self):
        """ Redirección: Master -> Asignatura (Portada) """
        super()._compute_website_url()
        for slide in self:
            if slide.asignatura_id and slide.id:
                # SIMPLIFICACIÓN ESTABILIDAD: Redirigimos a la portada de la Asignatura.
                slide.website_url = slide.asignatura_id.website_url

    def _action_mark_completed(self):
        """ 
        Evitar que los contenidos evaluables se marquen como completados 
        solo por visitarlos. Deben completarse vía Examen, Certificación o Archivo.
        """
        auto_completable = self.filtered(lambda s: not s.es_evaluable)
        if auto_completable:
            return super(Slide, auto_completable)._action_mark_completed()
        return False


