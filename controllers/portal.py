# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

class UniversityPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        """ Add 'My Grades' count to portal home """
        values = super()._prepare_home_portal_values(counters)
        if 'grades_count' in counters:
            # Contamos cursos donde hay al menos una nota
            partner = request.env.user.partner_id
            # Usamos sudo() porque el alumno no tiene permisos de lectura directos sobre slide.channel.partner
            # pero filtramos explícitamente por su partner_id para seguridad.
            count = request.env['slide.channel.partner'].sudo().search_count([
                ('partner_id', '=', partner.id),
                ('channel_id.tipo_curso', '!=', 'asignatura') # Contamos Masters/Micros
            ])
            values['grades_count'] = count
        return values

    @http.route(['/my/grades', '/my/grades/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_grades(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        # Sudo para saltar reglas de registro, confiando en el dominio estricto
        SlideChannelPartner = request.env['slide.channel.partner'].sudo()

        domain = [
            ('partner_id', '=', partner.id),
            ('channel_id.tipo_curso', '!=', 'asignatura') # Solo contenedores principales
        ]

        # Paginación (por si tiene mil cursos)
        grade_count = SlideChannelPartner.search_count(domain)
        pager = portal_pager(
            url="/my/grades",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=grade_count,
            page=page,
            step=10
        )

        # Buscar Masters y Micros
        courses = SlideChannelPartner.search(domain, limit=10, offset=pager['offset'])
        
        values.update({
            'date': date_begin,
            'courses': courses,
            'page_name': 'grades',
            'pager': pager,
            'default_url': '/my/grades',
        })
        return request.render("elearning_universidad.portal_my_grades", values)

    @http.route(['/my/grades/certificate/<int:gradebook_id>'], type='http', auth="user", website=True)
    def portal_my_grade_certificate(self, gradebook_id, download=False, **kw):
        """ Allow students to download/preview their certificate """
        # 1. Fetch record con seguridad explícita (sudo + ownership check)
        gradebook = request.env['slide.channel.partner'].sudo().browse(gradebook_id)
        
        # 2. Verificar existencia y propiedad
        if not gradebook.exists() or gradebook.partner_id != request.env.user.partner_id:
            return request.not_found()
            
        # 3. Verificar si tiene título emitido
        if not gradebook.titulo_emitido:
            return request.redirect('/my/grades')

        # 4. Buscar PDF adjunto (misma lógica que backend)
        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'slide.channel.partner'),
            ('res_id', '=', gradebook.id),
            ('mimetype', '=', 'application/pdf')
        ], order='create_date desc', limit=1)

        if not attachment:
            # Fallback elegante si no hay adjunto físico
            return request.not_found()

        # 5. Servir archivo
        # 'inline' para preview (navegador), 'attachment' para forzar descarga
        disposition = 'attachment' if download else 'inline'
        
        # Forzamos los headers correctos para la respuesta
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'{disposition}; filename={attachment.name}'),
        ]
        
        return request.make_response(
            attachment.raw,
            headers=headers
        )
