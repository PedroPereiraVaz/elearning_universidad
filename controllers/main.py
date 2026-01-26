from odoo import http, _
from odoo.http import request
import base64

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
                'estado_evaluacion': 'pendiente_presentar'
            })

        # No permitir resubir si ya está evaluado y confirmado (seguridad extra)
        if eval_record.estado_evaluacion == 'evaluado':
            return request.redirect(slide.website_url)

        # 5. Guardar el archivo y actualizar estado
        eval_record.write({
            'archivo_entrega': base64.b64encode(file_content) if file_content else False,
            'nombre_archivo': file.filename,
            'estado_evaluacion': 'pendiente_revision',
            'fecha_entrega': http.fields.Datetime.now()
        })

        # 6. Redirigir de vuelta al contenido con un parámetro de éxito
        return request.redirect(slide.website_url + "?delivery_success=1")
