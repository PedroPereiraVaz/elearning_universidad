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
