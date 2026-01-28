from odoo import http, fields, _
from odoo.http import request
from odoo.addons.website_slides.controllers.main import WebsiteSlides

import base64

class UniversityWebsiteSlides(WebsiteSlides):
    
    def _get_university_domain(self):
        """ Filtro base para ocultar Asignaturas y Cursos no publicados por la Universidad """
        return [('tipo_curso', '!=', 'asignatura'), ('estado_universidad', '=', 'publicado')]

    @http.route('/slides', type='http', auth="public", website=True, sitemap=True)
    def slides_channel_home(self, **post):
        """ Sobrescribimos la home para filtrar Asignaturas y Cursos no publicados """
        response = super().slides_channel_home(**post)
        
        # Si la respuesta es una renderización, filtramos los datos
        if response.qcontext:
            # Filtramos las listas estándar (Popular, Newest, etc)
            for list_name in ['channels_my', 'channels_popular', 'channels_newest']:
                if list_name in response.qcontext:
                    channels = response.qcontext[list_name]
                    # Filtramos en memoria para no romper la lazy evaluation si es posible,
                    # pero comúnmente es un recordset.
                    if channels:
                        # Ocultar asignaturas y ocultar no publicados (Defensa en profundidad)
                        # Nota: estado_universidad ya debería estar filtrado si website_published=False,
                        # pero este doble check evita fugas si alguien fuerza website_published=True manualmente.
                        filtered = channels.filtered(
                            lambda c: c.tipo_curso != 'asignatura' and c.estado_universidad == 'publicado'
                        )
                        response.qcontext[list_name] = filtered
        
        return response

    @http.route('/slides/all', type='http', auth="public", website=True, sitemap=True)
    def slides_channel_all(self, slide_type=None, my=False, **post):
        """ Sobrescribimos la vista 'All Courses' para ocultar asignaturas """
        response = super().slides_channel_all(slide_type, my, **post)
        if response.qcontext.get('channels'):
             response.qcontext['channels'] = response.qcontext['channels'].filtered(
                 lambda c: c.tipo_curso != 'asignatura' and c.estado_universidad == 'publicado'
             )
        return response

    def _slide_channel_all_values(self, slide_category=None, slug_tags=None, my=False, **post):
        """ Sobrescribimos la obtención de datos para búsquedas JSON/AJAX y /slides/all """
        values = super()._slide_channel_all_values(slide_category, slug_tags, my, **post)
        
        # FILTRO CENTRALIZADO: Ocultar asignaturas y no publicados
        if values.get('channels'):
            values['channels'] = values['channels'].filtered(
                lambda c: c.tipo_curso != 'asignatura' and c.estado_universidad == 'publicado'
            )
            
        return values
        
    @http.route([
        '/slides/<model("slide.channel"):channel>',
        '/slides/<model("slide.channel"):channel>/page/<int:page>',
        '/slides/<model("slide.channel"):channel>/tag/<model("slide.tag"):tag>',
        '/slides/<model("slide.channel"):channel>/tag/<model("slide.tag"):tag>/page/<int:page>',
        '/slides/<model("slide.channel"):channel>/category/<model("slide.slide"):category>',
        '/slides/<model("slide.channel"):channel>/category/<model("slide.slide"):category>/page/<int:page>',
    ], type='http', auth="public", website=True, sitemap=WebsiteSlides.sitemap_slide)
    def channel(self, channel, category=None, tag=None, page=1, slide_type=None, search=None, **kw):
        """ 
        Manejo de navegación Master -> Asignatura 
        """
        channel_id = channel.id if channel else kw.get('channel_id')
        
        # 1. Inyección para breadcrumbs/navegación
        # Llamamos a super pasando explícitamente channel_id para evitar el fallo en validaciones upstream
        response = super().channel(channel=channel, category=category, tag=tag, page=page, slide_type=slide_type, search=search, channel_id=channel_id, **kw)
        
        if channel.tipo_curso == 'asignatura' and channel.master_id:
            # Inyectamos el master en el contexto
            response.qcontext['parent_master'] = channel.master_id
            
        return response



class UniversitySlideController(http.Controller):

    @http.route('/slides/slide/upload_delivery', type='http', auth='user', methods=['POST'], website=True)
    def slide_upload_delivery(self, slide_id, **post):
        # 1. Recuperar el slide y validar que es un entregable
        slide = request.env['slide.slide'].browse(int(slide_id))
        if not slide.exists() or slide.slide_category != 'delivery':
            return request.redirect('/slides')

        # 2. Obtener el archivo del formulario
        file = post.get('file')
        if not file:
            return request.redirect(slide.website_url)

        # 3. Validar límite de tamaño (MB)
        limit_mb = slide.channel_id.upload_limit_mb or 10
        file_content = file.read()
        if len(file_content) > limit_mb * 1024 * 1024:
            # Mostramos un error simple (podría mejorarse con notificaciones de Odoo)
            return request.render('website.http_error', {
                'status_code': _('Archivo demasiado grande'),
                'status_message': _('El límite para este curso es de %s MB. Por favor, comprima el archivo e inténtelo de nuevo.') % limit_mb
            })

        # 4. Localizar o inicializar el registro de seguimiento slide.slide.partner
        # Usamos SUDO para asegurar que el registro se cree/actualice incluso si hay restricciones de escritura
        eval_record = request.env['slide.slide.partner'].sudo().search([
            ('slide_id', '=', slide.id),
            ('partner_id', '=', request.env.user.partner_id.id)
        ], limit=1)

        if not eval_record:
            eval_record = request.env['slide.slide.partner'].sudo().create({
                'slide_id': slide.id,
                'partner_id': request.env.user.partner_id.id,
                'channel_id': slide.channel_id.id,
                'estado_evaluacion': 'pendiente_revision'
            })

        # No permitir resubir si ya está evaluado y confirmado (seguridad extra)
        if eval_record.estado_evaluacion == 'evaluado':
            return request.redirect(slide.website_url)

        # 5. Guardar el archivo y actualizar estado
        eval_record.write({
            'archivo_entrega': base64.b64encode(file_content) if file_content else False,
            'nombre_archivo': file.filename,
            'estado_evaluacion': 'pendiente_revision',
            'fecha_entrega': fields.Datetime.now()
        })

        # 6. Marcar como completado automáticamente
        # Nota: slide.action_mark_completed() marca para el usuario actual.
        slide.action_mark_completed()

        # 7. Redirigir de vuelta al contenido con un parámetro de éxito
        return request.redirect(slide.website_url + "?delivery_success=1")
        