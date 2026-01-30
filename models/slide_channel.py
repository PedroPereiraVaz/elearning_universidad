from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError
from odoo.osv import expression
from markupsafe import Markup

class CanalSlide(models.Model):
    _inherit = 'slide.channel'

    # --- Propiedades de la Universidad ---
    # Inmutable siempre (definido por el menú/acción).
    tipo_curso = fields.Selection([
        ('master', 'Master'),
        ('microcredencial', 'Microcredencial'),
        ('asignatura', 'Asignatura')
    ], string="Tipo", default='asignatura', required=True, tracking=True)

    @api.model
    def _search_get_detail(self, website, order, options):
        """ 
        Sobrescribimos el método de búsqueda global del sitio web.
        Excluimos Asignaturas y Cursos No Publicados de los resultados de búsqueda.
        """
        search_details = super()._search_get_detail(website, order, options)
        
        # Odoo devuelve un dict con 'base_domain'.
        # Usamos 'or []' y list() para asegurar compatibilidad.
        original_domain = list(search_details.get('base_domain') or [])
        
        # AÑADIR FILTROS:
        # 1. Ocultar Asignaturas (tipo_curso != asignatura)
        # 2. Ocultar No Publicados (estado_universidad == publicado)
        filters = [('tipo_curso', '!=', 'asignatura'), ('estado_universidad', '=', 'publicado')]
        
        # Concatenación simple (Implicit AND)
        # IMPORTANTE: base_domain es una LISTA DE DOMINIOS (List[List[Tuple]]).
        # Debemos añadir nuestros filtros como una lista completa dentro de esa lista.
        search_details['base_domain'] = original_domain + [filters]
        return search_details

    # --- Acceso Campo Core Restringido ---
    # Odoo restringe channel_partner_ids a Officer. Ampliamos acceso.
    channel_partner_ids = fields.One2many(
        groups="website_slides.group_website_slides_officer,elearning_universidad.grupo_personal_docente,elearning_universidad.grupo_director_academico"
    )

    estado_universidad = fields.Selection([
        ('borrador', 'Borrador'),
        ('presentado', 'Presentado'),
        ('rechazado', 'Rechazado'),
        ('subsanacion', 'Subsanación'),
        ('programado', 'Programado'),
        ('publicado', 'Publicado'),
        ('finalizado', 'Finalizado')
    ], string='Estado Universidad', default='borrador', required=True, tracking=True)

    # Proxy para UI separada en Masters
    slide_ids_master = fields.One2many('slide.slide', 'channel_id', string="Contenido (Master)")

    motivo_rechazo = fields.Text(string='Motivo de Rechazo', readonly=True)
    fecha_programada_publicacion = fields.Datetime(string='Fecha Programada de Publicación')

    # --- Control de Seguridad UI ---
    can_manage_config = fields.Boolean(
        string="Puede Gestionar Configuración",
        compute='_compute_security_fields',
        help="Controla acceso a Opciones, Nombre, Tipo."
    )
    can_see_financials = fields.Boolean(
        string="Puede Ver Financieros",
        compute='_compute_security_fields',
        help="Controla acceso a Precio, Venta."
    )
    can_manage_members = fields.Boolean(
        string="Puede Gestionar Miembros",
        compute='_compute_security_fields',
        help="Controla botón de invitar/agregar miembros."
    )
    is_university_admin = fields.Boolean(
        string="Es Administrador de Universidad",
        compute='_compute_security_fields'
    )
    is_exclusive_teacher = fields.Boolean(
        string="Es Solo Docente",
        compute='_compute_security_fields',
        help="Verdadero si el usuario es docente pero NO director ni admin."
    )

    @api.depends('tipo_curso', 'director_academico_ids', 'personal_docente_ids')
    @api.depends_context('uid')
    def _compute_security_fields(self):
        user = self.env.user
        is_admin = user.has_group('elearning_universidad.grupo_administrador_universidad')
        is_director_group = user.has_group('elearning_universidad.grupo_director_academico')
        is_teacher_group = user.has_group('elearning_universidad.grupo_personal_docente')
        
        for record in self:
            # Detectar si el usuario es Director de ESTE curso específico
            # O si es Asignatura (donde el rol de grupo Director suele prevalecer)
            # Simplificación: Si tienes grupo Director, gestionas configuración si estás asignado o si eres admin.
            # Pero para el campo 'upload_limit_mb', el director pueda modificarlo.
            
            is_responsible_director = is_director_group and (
                user.id in record.director_academico_ids.ids or 
                record.create_uid.id == user.id
            )
            
            # 1. Configuración (Nombre, Opciones, Tipo, Upload Limit)
            if is_admin:
                record.can_manage_config = True
            elif is_responsible_director:
                record.can_manage_config = True 
            elif is_director_group and record.tipo_curso == 'asignatura':
                record.can_manage_config = True 
            else:
                record.can_manage_config = False # Docente 

            # 2. Financieros (Precio)
            record.can_see_financials = is_admin 
            
            # 3. Miembros
            # Director Académico SIEMPRE gestiona miembros en Asignaturas (igual que config)
            if record.tipo_curso == 'asignatura' and is_director_group:
                record.can_manage_members = True
            else:
                record.can_manage_members = is_admin or is_responsible_director

            # 4. Helpers UI
            record.is_university_admin = is_admin
            record.is_exclusive_teacher = is_teacher_group and not is_director_group and not is_admin

    # --- Permisos de Contenido (Override) ---
    @api.depends('user_id', 'director_academico_ids', 'personal_docente_ids')
    def _compute_can_upload(self):
        """ Controla quién puede crear contenido en el curso """
        super()._compute_can_upload()
        for record in self:
            if record.can_upload:
                continue
            
            # Permitir si es Staff del curso
            user_id = self.env.uid
            if (user_id in record.director_academico_ids.ids or 
                user_id in record.personal_docente_ids.ids or 
                self.env.user.has_group('elearning_universidad.grupo_administrador_universidad')):
                record.can_upload = True

    @api.depends('user_id', 'director_academico_ids', 'personal_docente_ids')
    def _compute_can_publish(self):
        """ Controla quién puede publicar contenido en el curso """
        super()._compute_can_publish()
        for record in self:
            if record.can_publish:
                continue
            
            # Permitir si es Staff del curso
            user_id = self.env.uid
            if (user_id in record.director_academico_ids.ids or 
                user_id in record.personal_docente_ids.ids or
                self.env.user.has_group('elearning_universidad.grupo_administrador_universidad')):
                record.can_publish = True

    # --- Roles Académicos --- 
    director_academico_ids = fields.Many2many(
        'res.users', 
        'slide_channel_director_rel', 
        'channel_id', 
        'user_id', 
        string='Directores Académicos',
        domain=lambda self: [
            ('groups_id', 'in', self.env.ref('elearning_universidad.grupo_director_academico').id),
            ('groups_id', 'not in', self.env.ref('elearning_universidad.grupo_administrador_universidad').id)
        ]
    )
    personal_docente_ids = fields.Many2many(
        'res.users', 
        'slide_channel_docente_rel', 
        'channel_id', 
        'user_id', 
        string='Personal Docente',
        domain=lambda self: [
            ('groups_id', 'in', self.env.ref('elearning_universidad.grupo_personal_docente').id),
            ('groups_id', 'not in', self.env.ref('elearning_universidad.grupo_administrador_universidad').id)
        ]
    )

    # --- Relaciones Jerárquicas ---
    master_id = fields.Many2one(
        'slide.channel', 
        string='Master Relacionado',
        domain=[('tipo_curso', '=', 'master')],
        help="El Master al que pertenece esta asignatura."
    )
    
    asignatura_ids = fields.One2many(
        'slide.channel', 
        'master_id', 
        string='Asignaturas Contenidas',
        domain=[('tipo_curso', '=', 'asignatura')]
    )

    # --- Costes ---

    precio_curso = fields.Float(
        string='Precio del Curso', 
        digits='Product Price',
        help="Precio establecido manualmente por la Universidad."
    )

    # --- Límites ---
    upload_limit_mb = fields.Integer(
        string='Límite de Subida (MB)', 
        default=10, 
        help="Tamaño máximo permitido para los entregables de los alumnos (0 para ilimitado)."
    )

    # --- Títulos ---
    tiene_titulo = fields.Boolean(string='Emitir Título', default=False)

    # --- Campos Estadísticos Técnicos ---
    nbr_sub_course = fields.Integer(string='Número de Asignaturas', compute='_compute_slides_statistics', store=True, compute_sudo=True)
    nbr_delivery = fields.Integer(string='Número de Entregables', compute='_compute_slides_statistics', store=True, compute_sudo=True)
    nbr_exam = fields.Integer(string='Número de Exámenes', compute='_compute_slides_statistics', store=True, compute_sudo=True)
    
    @api.model
    def _get_plantillas_titulo(self):
        try:
            return self.env['survey.survey']._fields['certification_report_layout'].selection
        except (AttributeError, KeyError):
            return [('modern_gold', 'Modern Gold'), ('modern_purple', 'Modern Purple'), ('classic_blue', 'Classic Blue')]

    plantilla_titulo = fields.Selection(
        selection='_get_plantillas_titulo',
        string='Plantilla del Título',
        default='modern_gold'
    )

    politica_emision = fields.Selection([
        ('automatica', 'Automática (al cerrar acta)'),
        ('manual', 'Manual (requiere validación)')
    ], string='Política de Emisión', default='manual',  help="Define si el título se encola automáticamente al aprobar el curso o requiere validación manual.")


    # --- Campo para OPTIMIZAR REGLAS DE SEGURIDAD ---
    # Este campo almacena TODOS los docentes vinculados a este curso (directos + heredados de asignaturas)
    # Permite simplificar las reglas de registro y evitar joins complejos o recursiones.
    all_personal_docente_ids = fields.Many2many(
        'res.users',
        'slide_channel_all_docentes_rel',
        'channel_id', 'user_id',
        string='Todos los Docentes (Calculado)',
        compute='_compute_all_personal_docente_ids',
        store=True,
        compute_sudo=True
    )

    @api.depends('personal_docente_ids', 'asignatura_ids.personal_docente_ids', 'master_id.personal_docente_ids')
    def _compute_all_personal_docente_ids(self):
        for record in self:
            docentes = record.personal_docente_ids
            # Si es Master, incluimos los docentes de sus asignaturas
            if record.tipo_curso == 'master':
                docentes |= record.asignatura_ids.mapped('personal_docente_ids')
            
            # Si es Asignatura, incluimos los docentes del Master (Visibilidad Ascendente)
            if record.master_id:
                docentes |= record.master_id.personal_docente_ids

            record.all_personal_docente_ids = docentes

    # --- Campos de Visualización (Text Strings) para evitar problemas de ACL en Vistas ---
    director_academico_names = fields.Char(string='Directores (Texto)', compute='_compute_staff_names', compute_sudo=True, store=True)
    personal_docente_names = fields.Char(string='Docentes (Texto)', compute='_compute_staff_names', compute_sudo=True, store=True)

    @api.depends('director_academico_ids', 'master_id.director_academico_ids', 'all_personal_docente_ids')
    def _compute_staff_names(self):
        for record in self:
            # DIRECTORES: Bypass ORM/Domain filtering using explicit SQL to guarantee simple display visibility
            # This ensures that if a user is linked in the DB, they show up, even if they lost the 'group' required by the domain.
            dir_ids = set()
            try:
                # 1. Direct fetch from relation table for this channel
                self.env.cr.execute("SELECT user_id FROM slide_channel_director_rel WHERE channel_id = %s", (record.id,))
                dir_ids.update(row[0] for row in self.env.cr.fetchall())
                
                # 2. If it's an Asignatura (with Master), fetch from Master
                if record.master_id:
                    self.env.cr.execute("SELECT user_id FROM slide_channel_director_rel WHERE channel_id = %s", (record.master_id.id,))
                    dir_ids.update(row[0] for row in self.env.cr.fetchall())
                
                if dir_ids:
                    # Browse as sudo to read names
                    directors = self.env['res.users'].sudo().browse(list(dir_ids))
                    record.director_academico_names = ', '.join(directors.mapped('name'))
                else:
                    record.director_academico_names = ''
            except Exception:
                # Safe fallback to ORM if table doesn't exist yet (in memory)
                # But logic dictates we stick to robust display.
                # Just fallback to empty if crash.
                record.director_academico_names = ''

            # DOCENTES: Keep ORM logic as it was working fine
            record.personal_docente_names = ', '.join(record.all_personal_docente_ids.mapped('name'))

    # --- Computes de Lógica Académica ---
    @api.depends('slide_ids.completion_time', 'master_id.slide_ids.completion_time', 'tipo_curso')
    def _compute_total_time(self):
        super()._compute_total_time()
        for record in self:
            if record.tipo_curso == 'asignatura' and record.master_id:
                # La duración de la asignatura es la que se define en su slide representativo dentro del Master
                slide_en_master = record.master_id.slide_ids.filtered(lambda s: s.asignatura_id == record)
                if slide_en_master:
                    record.total_time = sum(slide_en_master.mapped('completion_time'))

    # --- Sincronización con Productos de Odoo ---
    def _sincronizar_producto_universidad(self):
        """ 
        Logica de mantenimiento automático del producto vinculado. Asegura relación 1:1 entre Curso de Pago y Producto.
        """
        for curso in self:
            if curso.enroll == 'payment' and curso.precio_curso > 0 and curso.tipo_curso in ['master', 'microcredencial']:
                if not curso.product_id:
                    # CREAR PRODUCTO (Fallback por si se llama manual o update)
                    product = self.env['product.product'].sudo().create({
                        'name': curso.name,
                        'list_price': curso.precio_curso,
                        'type': 'service',
                        'service_tracking': 'course',
                        'invoice_policy': 'order',
                        'is_published': True,
                        'uom_id': self.env.ref('uom.product_uom_unit').id,
                        'uom_po_id': self.env.ref('uom.product_uom_unit').id,
                    })
                    curso.sudo().write({'product_id': product.id})
                else:
                    # ACTUALIZAR PRODUCTO
                    vals_prod = {}
                    if curso.product_id.name != curso.name:
                        vals_prod['name'] = curso.name
                    if curso.product_id.list_price != curso.precio_curso:
                        vals_prod['list_price'] = curso.precio_curso
                    if not curso.product_id.active:
                        vals_prod['active'] = True # Reactivar si estaba archivado
                    
                    if vals_prod:
                        curso.product_id.sudo().write(vals_prod)
            
            elif curso.enroll != 'payment' and curso.product_id:
                # ARCHIVAR PRODUCTO (Si deja de ser de pago)
                if curso.product_id.active:
                    curso.product_id.sudo().write({'active': False})

    def _sincronizar_slide_master(self):
        """ 
        Automatización: Cuando una Asignatura se vincula a un Master,
        creamos/actualizamos su representación como Slide (contenido) en ese Master.
        """
        Slide = self.env['slide.slide'].sudo()
        for curso in self:
            if curso.tipo_curso == 'asignatura' and curso.master_id:
                # RECURSION STOPPER: Check if we are reacting to a change from the Slide side
                if self.env.context.get('avoid_recursive_sync'):
                    continue

                # 1. Buscamos si ya existe el slide en el Master
                slide_existente = Slide.search([
                    ('channel_id', '=', curso.master_id.id),
                    ('asignatura_id', '=', curso.id),
                    ('slide_category', '=', 'sub_course')
                ], limit=1)

                vals_slide = {
                    'name': curso.name,
                    'channel_id': curso.master_id.id,
                    'slide_category': 'sub_course',
                    'asignatura_id': curso.id,
                    'is_published': curso.is_published,
                    'es_evaluable': True, # Requisito: Marcar automáticamente como evaluable
                    'sequence': 100 # Por defecto al final
                }

                if slide_existente:
                    # Usamos SUDO y contexto para evitar el envío de correos automáticos "Nuevo contenido publicado"
                    # al sincronizar la asignatura. PASAMOS EL FLAG para que el slide no intente escribir de vuelta en nosotros.
                    slide_existente.sudo().with_context(mail_notrack=True, mail_create_nosubscribe=True, avoid_recursive_sync=True).write(vals_slide)
                else:
                    Slide.with_context(automation_create=True, mail_notrack=True, mail_create_nosubscribe=True, avoid_recursive_sync=True).create(vals_slide)
            
            # Limpieza: Si cambió de master o dejó de ser asignatura (improbable por inmutabilidad),
            # deberíamos borrar los slides antiguos que apunten a este curso pero estén en otros masters.
            slides_huerfanos = Slide.search([
                ('asignatura_id', '=', curso.id),
                ('slide_category', '=', 'sub_course')
            ])
            if curso.master_id:
                slides_huerfanos = slides_huerfanos.filtered(lambda s: s.channel_id != curso.master_id)
            
            if slides_huerfanos:
                slides_huerfanos.unlink()

    # --- Acciones de Workflow (Estados) con Validaciones ---

    def _format_notification_html(self, titulo, mensaje, tipo='info'):
        """ Genera un HTML estético para las notificaciones del chatter """
        colors = {
            'success': '#d4edda', # Verde claro
            'warning': '#fff3cd', # Amarillo claro
            'danger': '#f8d7da',  # Rojo claro
            'info': '#d1ecf1',    # Azul claro
            'primary': '#cce5ff', # Azul
            'secondary': '#e2e3e5' # Gris
        }
        text_colors = {
            'success': '#155724',
            'warning': '#856404',
            'danger': '#721c24',
            'info': '#0c5460',
            'primary': '#004085',
            'secondary': '#383d41'
        }
        icons = {
            'success': 'check-circle',
            'warning': 'exclamation-triangle',
            'danger': 'times-circle',
            'info': 'info-circle',
            'primary': 'bell',
            'secondary': 'archive'
        }
        
        bg_color = colors.get(tipo, '#fff')
        text_color = text_colors.get(tipo, '#000')
        icon = icons.get(tipo, 'info-circle')
        
        return Markup(f"""
            <div style="background-color: {bg_color}; color: {text_color}; padding: 15px; border-radius: 5px; border-left: 5px solid {text_color}; margin-bottom: 10px;">
                <h5 style="margin: 0; font-weight: bold; display: flex; align-items: center;">
                    <i class="fa fa-{icon}" style="margin-right: 10px;"></i> {titulo}
                </h5>
                <p style="margin: 5px 0 0 0; font-size: 14px;">{mensaje}</p>
            </div>
        """)

    def _notificar_administradores(self, titulo, mensaje, tipo='info'):
        """ Notifica a todos los administradores de la universidad """
        grupo_admin = self.env.ref('elearning_universidad.grupo_administrador_universidad')
        admins = grupo_admin.users.mapped('partner_id')
        
        html_body = self._format_notification_html(titulo, mensaje, tipo)
        
        for record in self:
            record.message_post(
                body=html_body,
                partner_ids=admins.ids,
                message_type='notification'
            )

    def _sincronizar_seguidores_staff(self):
        """ 
        Agrega a Directores y Docentes como seguidores del curso (Chatter)
        """
        for record in self:
            partners = record.director_academico_ids.mapped('partner_id') | record.personal_docente_ids.mapped('partner_id')
            if partners:
                # Suscribimos con subtipo 'discusiones' (mt_comment) por defecto
                record.message_subscribe(partner_ids=partners.ids)
    
    @api.constrains('estado_universidad')
    def _check_requisitos_publicacion(self):
        """ Validaciones críticas antes de publicar o programar """
        for record in self:
            if record.estado_universidad in ['programado', 'publicado']:
                # 1. Director Académico Obligatorio (Master/Micro)
                # Para asignaturas lo heredamos, así que verificamos que el Master lo tenga
                if record.tipo_curso in ['master', 'microcredencial']:
                    if not record.director_academico_ids:
                        raise ValidationError(f"El curso '{record.name}' debe tener asignado al menos un Director Académico.")
                
                # 2. Master Obligatorio (Asignatura)
                if record.tipo_curso == 'asignatura':
                    if not record.master_id:
                        raise ValidationError(f"La asignatura '{record.name}' debe pertenecer a un Master para ser publicada.")
                    # Verificación indirecta: si el master no tiene director, la asignatura tampoco lo tendrá
                    if not record.director_academico_ids:
                         # Intentamos recuperar del master si falla
                         if record.master_id.director_academico_ids:
                             record.director_academico_ids = record.master_id.director_academico_ids
                         else:
                             raise ValidationError(f"El Master vinculado a la asignatura '{record.name}' no tiene Director Académico asignado.")

                # 3. Precio Obligatorio (Si es de pago)
                if record.enroll == 'payment' and record.precio_curso <= 0:
                     raise ValidationError(f"El curso '{record.name}' está configurado como 'De Pago' pero el precio es 0.00.")

                # 4. Plantilla de Título (Si emite título)
                if record.tiene_titulo and not record.plantilla_titulo:
                    raise ValidationError(f"El curso '{record.name}' emite título pero no tiene seleccionada ninguna Plantilla.")

                # 5. Duración de Asignatura (Requisito Académico)
                # CAMBIO: Usamos ESTRICTAMENTE la duración definida en la ficha del Master (Slide), no el contenido interno.
                if record.tipo_curso == 'asignatura':
                   master_slide = self.env['slide.slide'].search([
                        ('asignatura_id', '=', record.id),
                        ('slide_category', '=', 'sub_course')
                    ], limit=1)
                    
                   if not master_slide or master_slide.completion_time <= 0:
                        raise ValidationError(f"La asignatura '{record.name}' debe tener una duración mayor a 0 horas definida en el Master para ser publicada.")

    @api.onchange('master_id')
    def _onchange_master_id_directores(self):
        """ Heredar directores del Master automáticamente """
        if self.tipo_curso == 'asignatura' and self.master_id:
            self.director_academico_ids = self.master_id.director_academico_ids

    def action_presentar(self):
        for record in self:
            # Validación Previa
            if record.tipo_curso in ['master', 'microcredencial'] and not record.director_academico_ids:
                 raise ValidationError(_("Debe asignar al menos un Director Académico antes de presentar el curso."))
            
            if record.estado_universidad != 'borrador':
                raise ValidationError("Solo se pueden presentar cursos en estado Borrador.")
            record.estado_universidad = 'presentado'
            record._notificar_administradores(
                _("Nuevo curso presentado"), 
                _("El curso '%s' ha sido presentado para revisión.") % record.name,
                tipo='info'
            )

    def action_rechazar(self, motivo):
        if not self.env.user.has_group('elearning_universidad.grupo_administrador_universidad'):
            raise ValidationError("Solo un Administrador de Universidad puede rechazar cursos.")
        for record in self:
            record.write({
                'estado_universidad': 'rechazado',
                'motivo_rechazo': motivo
            })
            # Notificación de Rechazo con Motivo
            html_body = record._format_notification_html(
                _("Curso Rechazado"),
                _("El curso ha sido rechazado por el Administrador.<br/><strong>Motivo:</strong> %s") % motivo,
                tipo='danger'
            )
            record.message_post(body=html_body, subtype_xmlid='mail.mt_comment')

    def action_subsanar(self):
        """ Equivale a volver a presentar tras un rechazo """
        for record in self:
            if record.estado_universidad != 'rechazado':
                raise ValidationError("Solo se pueden subsanar cursos rechazados.")
            record.estado_universidad = 'subsanacion'
            record._notificar_administradores(
                _("Curso subsanado"), 
                _("El curso '%s' ha sido re-presentado tras subsanación.") % record.name,
                tipo='warning'
            )

    def action_confirmar_programacion(self):
        """ Wrapper para botón de vista: Lee fecha del formulario y llama a acción lógica """
        for record in self:
            if not record.fecha_programada_publicacion:
                raise ValidationError("Debe establecer una 'Fecha Programada' antes de confirmar.")
            record.action_programar(record.fecha_programada_publicacion)

    def action_programar(self, fecha):
        if not self.env.user.has_group('elearning_universidad.grupo_administrador_universidad'):
            raise ValidationError("Solo un Administrador de Universidad puede programar cursos.")
        for record in self:
            record.write({
                'estado_universidad': 'programado',
                'fecha_programada_publicacion': fecha
            })
            # La constraint _check_requisitos_publicacion saltará aquí al guardar 'programado'
            # Notificación de Programación
            html_body = record._format_notification_html(
                _("Publicación Programada"),
                _("El curso se ha programado para publicarse el <strong>%s</strong>.") % fecha,
                tipo='info'
            )
            record.message_post(body=html_body, subtype_xmlid='mail.mt_comment')

    def action_publicar(self):
        for record in self:
            es_admin = self.env.user.has_group('elearning_universidad.grupo_administrador_universidad')
            es_director = self.env.user.has_group('elearning_universidad.grupo_director_academico')
            
            if record.tipo_curso in ['master', 'microcredencial'] and not es_admin:
                raise ValidationError("Solo un Administrador de Universidad puede publicar Masters o Microcredenciales.")
            
            if record.tipo_curso == 'asignatura' and not es_director and not es_admin:
                raise ValidationError("Solo un Director Académico o Administrador puede publicar Asignaturas.")
            
            # SUDO para evitar errores de permisos/recursión al renderizar correos automáticos
            # (El sistema envía emails al notificar publicación, lo que puede chocar con las reglas de privacidad)
            record.sudo().write({
                'estado_universidad': 'publicado',
                'is_published': True
            })
            # La constraint saltará aquí si falla algo
            # Notificación de Publicación
            html_body = record._format_notification_html(
                _("Curso Publicado"),
                _("El curso ha sido publicado y ya es visible para los usuarios."),
                tipo='success'
            )
            record.message_post(body=html_body, subtype_xmlid='mail.mt_comment')

    def action_finalizar(self):
        if not self.env.user.has_group('elearning_universidad.grupo_administrador_universidad'):
            raise ValidationError("Solo un Administrador de Universidad puede finalizar cursos.")
        for record in self:
            if record.estado_universidad != 'publicado':
                raise ValidationError("Solo se pueden finalizar cursos publicados.")
            
            # 1. Finalizar el curso principal
            record.write({
                'estado_universidad': 'finalizado',
                'active': False,
                'is_published': False
            })

            # 2. CASCADA: Si es Master, finalizar sus asignaturas
            if record.tipo_curso == 'master' and record.asignatura_ids:
                record.asignatura_ids.sudo().write({
                    'estado_universidad': 'finalizado',
                    'active': False,
                    'is_published': False
                })

            # Notificación de Finalización
            html_body = record._format_notification_html(
                _("Curso Finalizado"),
                _("El curso ha sido finalizado y archivado."),
                tipo='secondary'
            )
            record.message_post(body=html_body, subtype_xmlid='mail.mt_comment')

    # --- Restricciones de Creación y Edición ---
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Determinamos tipo: viene en vals o en context
            tipo = vals.get('tipo_curso') or self.env.context.get('default_tipo_curso') or 'microcredencial'
            
            es_admin = self.env.user.has_group('elearning_universidad.grupo_administrador_universidad')
            es_director = self.env.user.has_group('elearning_universidad.grupo_director_academico')
            
            # Regla 1: Master y Micro SOLO Admin
            if tipo in ['master', 'microcredencial'] and not es_admin:
                raise AccessError(_("Solo un Administrador de Universidad puede crear Masters o Microcredenciales."))
            
            # Regla 2: Asignatura SOLO Admin o Director
            if tipo == 'asignatura':
                if not es_director and not es_admin:
                    raise AccessError(_("Solo un Director Académico o Administrador puede crear Asignaturas."))
                
                # INYECCIÓN DE DEFAULTS PARA ASIGNATURA (Evita llamada a write posterior)
                vals.update({
                    'enroll': 'invite',
                    'visibility': 'members',
                    'channel_type': 'training',
                    'precio_curso': 0.0,
                    'tiene_titulo': False
                })
                
                # HERENCIA SERVER-SIDE DE DIRECTORES (Blindaje extra si el campo es invisible)
                if 'director_academico_ids' not in vals and vals.get('master_id'):
                    master = self.env['slide.channel'].browse(vals['master_id'])
                    if master.director_academico_ids:
                        vals['director_academico_ids'] = [(6, 0, master.director_academico_ids.ids)]

            # FIX: Pre-creación de Producto para Cursos de Pago
            # Odoo exige 'product_id' si enroll='payment' al crear el registro.
            if vals.get('enroll') == 'payment' and not vals.get('product_id'):
                # Usamos los valores disponibles en vals
                name = vals.get('name') or 'Curso Universitario'
                price = vals.get('precio_curso', 0.0)
                
                product = self.env['product.product'].sudo().create({
                    'name': name,
                    'list_price': price,
                    'type': 'service',
                    'service_tracking': 'course',
                    'invoice_policy': 'order',
                    'is_published': True,
                    'uom_id': self.env.ref('uom.product_uom_unit').id,
                    'uom_po_id': self.env.ref('uom.product_uom_unit').id,
                })
                vals['product_id'] = product.id

        cursos = super().create(vals_list)
        # Sincronización producto y SLIDES DE MASTER
        for curso in cursos:
            curso._sincronizar_producto_universidad()
            if not self.env.context.get('avoid_slide_sync'):
                curso._sincronizar_slide_master()
            
            # Sincronización inicial de seguidores (Directores/Docentes)
            curso._sincronizar_seguidores_staff()
        
        return cursos

    @api.onchange('enroll')
    def _onchange_enroll_payment(self):
        """ Obliga a definir el nombre antes de marcar como pago y sugiere el precio """
        if self.enroll == 'payment':
            # Requisito: Debe tener Nombre (aunque no esté guardado aún)
            # Quitamos 'not self._origin' para permitir flujo: Poner Nombre -> Poner Pago -> Guardar
            if not self.name:
                self.enroll = 'invite'
                return {
                    'warning': {
                        'title': 'Nombre Requerido', 
                        'message': 'Para configurar un curso como "De Pago", primero debe escribir un Nombre para el curso.'
                    }
                }
            
            # Si ya tenemos precio y nombre, intentamos pre-sincronizar visualmente
            # NOTA: No creamos el producto en DB aquí para evitar huérfanos, 
            # pero la lógica de create/write lo hará al guardar.

    # --- DEFAULTS INTELIGENTES EN UI ---
    @api.onchange('tipo_curso')
    def _onchange_tipo_curso_universidad(self):
        if self.tipo_curso == 'asignatura':
            self.enroll = 'invite' # Por invitación (Miembros)
            self.visibility = 'members' # Solo miembros
            self.channel_type = 'training' # Formación (Mostrar en pantalla)
            self.precio_curso = 0.0
            self.tiene_titulo = False

    def write(self, vals):
        user = self.env.user
        is_admin = user.has_group('elearning_universidad.grupo_administrador_universidad')

        # Capturamos el estado previo de los staff para comparar (Logic for Unsubscribe)
        if 'director_academico_ids' in vals or 'personal_docente_ids' in vals:
            old_staff = {rec.id: (rec.director_academico_ids | rec.personal_docente_ids) for rec in self}
        else:
            old_staff = {}

        # Capture asginaturas antiguas para propagacion de bajas o altar (Membership Propagation)
        if 'asignatura_ids' in vals:
            old_asignaturas = {rec.id: rec.asignatura_ids for rec in self}
        else:
            old_asignaturas = {}

        if 'master_id' in vals:
            old_masters = {rec.id: rec.master_id for rec in self}
        else:
            old_masters = {}

        # 1. Bloqueo de Tipo (INMUTABLE)
        if 'tipo_curso' in vals:
            for record in self:
                if record.id and record.tipo_curso and vals['tipo_curso'] != record.tipo_curso:
                    # Excepción técnica: si se está creando
                    raise UserError(_("El Tipo de Curso es inmutable. No se puede cambiar."))

        # 2. Bloqueo de Publicación Web (Botón "Unpublished" -> "Published")
        if ('is_published' in vals or 'website_published' in vals):
             # Lógica condicional: Admin siempre, Director solo en Asignatura ASIGNADA
             if not is_admin:
                 is_director = user.has_group('elearning_universidad.grupo_director_academico')
                 if is_director:
                     # Verificamos cada registro:
                     for r in self:
                         if r.tipo_curso != 'asignatura':
                             raise AccessError(_("Solo los Administradores pueden publicar Masters o Microcredenciales."))
                         if user not in r.director_academico_ids and r.director_academico_ids:
                             raise AccessError(_("Solo el Director Académico asignado puede publicar esta Asignatura."))
                 else:
                    # Ni admin ni director
                    raise AccessError(_("No tiene permiso para publicar cursos."))

        # 3. Bloqueo de Estructura (Director/Docente solo tocan contenido)
        campos_estructurales = ['name', 'tipo_curso', 'precio_curso', 'promoted_tag_ids']
        if any(campo in vals for campo in campos_estructurales):
             if not is_admin:
                 is_director = user.has_group('elearning_universidad.grupo_director_academico')
                 if is_director:
                      for r in self:
                           if r.tipo_curso != 'asignatura':
                               raise AccessError(_("No puede editar este curso."))
                           if user not in r.director_academico_ids and r.director_academico_ids:
                               raise AccessError(_("Solo el Director Académico asignado puede editar esta Asignatura."))
                           
                           if 'precio_curso' in vals:
                               raise AccessError(_("No puede modificar el precio."))
                 else:
                     raise AccessError(_("No tiene permiso para modificar estas propiedades."))

        res = super().write(vals)
        
        # Sincronización de producto si cambian datos clave
        if any(campo in vals for campo in ['name', 'precio_curso', 'enroll', 'tipo_curso']):
            self.filtered(lambda c: c.tipo_curso in ['master', 'microcredencial'])._sincronizar_producto_universidad()
        
        # Sincronización de SLIDE EN MASTER (Nombre, Publicación, etc)
        if any(campo in vals for campo in ['name', 'master_id', 'is_published']):
             if not self.env.context.get('avoid_slide_sync'):
                 self._sincronizar_slide_master()

        # Propagación de matrícula (Add & Remove)
        if 'asignatura_ids' in vals:
            for master in self.filtered(lambda c: c.tipo_curso == 'master'):
                current_asignaturas = master.asignatura_ids
                previous_asignaturas = old_asignaturas.get(master.id, self.env['slide.channel'])
                
                socios = master.channel_partner_ids.mapped('partner_id')
                # Si el Master no tiene alumnos, no hay nada que propagar
                if not socios:
                    continue

                # 1. Nuevas Asignaturas -> Matricular
                new_asignaturas = current_asignaturas - previous_asignaturas
                if new_asignaturas:
                    new_asignaturas.sudo()._action_add_members(socios)
                
                # 2. Asignaturas Eliminadas -> Desmatricular
                removed_asignaturas = previous_asignaturas - current_asignaturas
                if removed_asignaturas:
                    removed_asignaturas.sudo()._remove_membership(socios.ids)
                    
        # Propagación Inversa: Si una Asignatura cambia de Master (se agrega/quita vía master_id)
        if 'master_id' in vals:
            for asignatura in self.filtered(lambda c: c.tipo_curso == 'asignatura'):
                current_master = asignatura.master_id
                previous_master = old_masters.get(asignatura.id, self.env['slide.channel'])
                
                # A. Cambio de Master (Add/Switch) -> Heredar alumnos del Nuevo Master
                if current_master and current_master != previous_master:
                    socios_master = current_master.channel_partner_ids.mapped('partner_id')
                    if socios_master:
                        asignatura.sudo()._action_add_members(socios_master)
                
                # B. Salida de Master (Remove/Switch) -> Eliminar alumnos del Viejo Master
                if previous_master and previous_master != current_master:
                    socios_old = previous_master.channel_partner_ids.mapped('partner_id')
                    if socios_old:
                        asignatura.sudo()._remove_membership(socios_old.ids)

        # Sincronización de SEGUIDORES (Nativo Odoo)
        if old_staff:
            for record in self:
                current_staff = record.director_academico_ids | record.personal_docente_ids
                previous_staff = old_staff.get(record.id, self.env['res.users'])
                
                # Nuevos seguidores
                to_add = (current_staff - previous_staff).mapped('partner_id')
                if to_add:
                    record.message_subscribe(partner_ids=to_add.ids)
                
                # Eliminados (Unsubscribe)
                to_remove = (previous_staff - current_staff).mapped('partner_id')
                if to_remove:
                    record.message_unsubscribe(partner_ids=to_remove.ids)
        elif 'director_academico_ids' in vals or 'personal_docente_ids' in vals:
             # Fallback por si old_staff estaba vacío pero es un create o similar (aunque esto es write)
             self._sincronizar_seguidores_staff()
        
        return res

    def unlink(self):
        # PROTECCIÓN DE BORRADO: Solo Administradores
        user = self.env.user
        if not user.has_group('elearning_universidad.grupo_administrador_universidad'):
            raise AccessError(_("Solo los Administradores de Universidad pueden eliminar cursos."))

        # Limpieza de slides representativos en Masters antes de borrar el curso
        Slide = self.env['slide.slide'].sudo()
        for curso in self:
            if curso.tipo_curso == 'asignatura':
                slides_vinculados = Slide.search([
                    ('asignatura_id', '=', curso.id),
                    ('slide_category', '=', 'sub_course')
                ])
                if slides_vinculados:
                    slides_vinculados.unlink()
        
        return super().unlink()

    @api.model
    def _cron_publicar_cursos_programados(self):
        """ CRON para publicar cursos cuya fecha programada haya llegado """
        cursos = self.search([
            ('estado_universidad', '=', 'programado'),
            ('fecha_programada_publicacion', '<=', fields.Datetime.now())
        ])
        for curso in cursos:
            # Llamamos a action_publicar con sudo para bypass de permisos en CRON
            curso.sudo().action_publicar()


    # --- Propagación de Matrículas (Altas y Bajas) ---
    def _action_add_members(self, target_partners, **kwargs):
        """ Al unirse a un Master, crea registros de seguimiento para contenidos evaluables """
        res = super()._action_add_members(target_partners, **kwargs)
        for curso in self:
            # 1. Proactividad: Asegurar registros de seguimiento para contenidos evaluables
            evaluable_slides = curso.slide_ids.filtered(lambda s: s.es_evaluable)
            if evaluable_slides:
                evaluable_slides.sudo()._asegurar_registros_seguimiento()
            
            # 2. Propagación recursiva para Masters
            if curso.tipo_curso == 'master' and curso.asignatura_ids:
                # Matriculamos recursivamente en las asignaturas usando sudo
                curso.asignatura_ids.sudo()._action_add_members(target_partners, **kwargs)
        return res

    def _remove_membership(self, partner_ids):
        """ Al desmatricular de un Master, se desmatricula automáticamente de sus asignaturas """
        res = super()._remove_membership(partner_ids)
        for curso in self:
            if curso.tipo_curso == 'master' and curso.asignatura_ids:
                # Desmatriculamos recursivamente de las asignaturas usando sudo
                curso.asignatura_ids.sudo()._remove_membership(partner_ids)
        return res

    @api.constrains('tipo_curso', 'master_id')
    def _verificar_jerarquia(self):
        for registro in self:
            if registro.tipo_curso == 'asignatura' and registro.master_id:
                if registro.master_id.tipo_curso != 'master':
                    raise ValidationError("Una 'Asignatura' solo puede estar vinculada a un 'Master'")
            
            if registro.tipo_curso == 'master' and registro.master_id:
                raise ValidationError("Un 'Master' no puede estar contenido en otro curso")
            
            if registro.tipo_curso == 'microcredencial':
                if registro.master_id:
                    raise ValidationError("Una 'Microcredencial' no puede estar contenida en otro curso")
                if registro.asignatura_ids:
                    raise ValidationError("Una 'Microcredencial' no puede contener 'Asignaturas'")

    
    def action_view_gradebook_students(self):
        """ Opens the list of students for this course in Gradebook mode """
        self.ensure_one()
        # Calculamos el ID de agrupación (Master) según el tipo de curso actual
        target_master_id = self.id if self.tipo_curso == 'master' else (self.master_id.id if self.master_id else False)
        
        return {
            'name': _('Alumnos de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'slide.channel.partner',
            'view_mode': 'list',
            'view_id': self.env.ref('elearning_universidad.view_slide_channel_partner_tree_gradebook').id,
            # Filtro Fundamental: Solo alumnos de este curso
            'domain': [('channel_id', '=', self.id)],
            'context': {
                'search_default_channel_id': self.id, 
                'default_channel_id': self.id,
                'default_gradebook_master_id': target_master_id
            }
        }
