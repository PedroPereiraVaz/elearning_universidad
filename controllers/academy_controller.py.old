from odoo import http, fields
from odoo.http import request
from odoo.addons.website_slides.controllers.main import WebsiteSlides
import base64


class AcademyWebsiteSlides(WebsiteSlides):
    
    @http.route('/slides', type='http', auth="public", website=True, sitemap=True)
    def slides_channel_home(self, **post):
        response = super().slides_channel_home(**post)
        if response.qcontext:
            # Filter sub-courses from lists
            for list_name in ['channels_my', 'channels_popular', 'channels_newest']:
                if list_name in response.qcontext:
                    # Resolve lazy if needed, but safe to just filter
                    # Need to check if it's a lazy object or recordset
                    channels = response.qcontext[list_name]
                    # We can't easily filter a lazy object without triggering it.
                    # But we want to filter the result.
                    # Let's define a wrapper or just simple filter because Odoo templates handle recordsets well.
                    # If it's tools.lazy, accessing it evaluates it.
                    filtered_channels = channels.filtered(lambda c: not c.is_subject)
                    response.qcontext[list_name] = filtered_channels
        return response

    def slides_channel_all_values(self, slide_category=None, slug_tags=None, my=False, **post):
        values = super().slides_channel_all_values(slide_category, slug_tags, my, **post)
        if 'channels' in values:
            values['channels'] = values['channels'].filtered(lambda c: not c.is_subject)
        return values

    @http.route([
        '/slides/<int:channel_id>',
        '/slides/<int:channel_id>/category/<int:category_id>',
        '/slides/<int:channel_id>/category/<int:category_id>/page/<int:page>',
        '/slides/<model("slide.channel"):channel>',
        '/slides/<model("slide.channel"):channel>/page/<int:page>',
        '/slides/<model("slide.channel"):channel>/tag/<model("slide.tag"):tag>',
        '/slides/<model("slide.channel"):channel>/tag/<model("slide.tag"):tag>/page/<int:page>',
        '/slides/<model("slide.channel"):channel>/category/<model("slide.slide"):category>',
        '/slides/<model("slide.channel"):channel>/category/<model("slide.slide"):category>/page/<int:page>',
    ], type='http', auth="public", website=True, sitemap=WebsiteSlides.sitemap_slide, readonly=True)
    def channel(self, channel=False, channel_id=False, **kwargs):
        response = super().channel(channel, channel_id, **kwargs)
        if response.qcontext.get('channel'):
            current_channel = response.qcontext['channel']
            if current_channel.is_subject:
                # Find parent master (slide referencing this channel as sub_course)
                parent_slide = request.env['slide.slide'].sudo().search([
                    ('sub_channel_id', '=', current_channel.id),
                    ('channel_id.academy_type', '=', 'master')
                ], limit=1)
                if parent_slide:
                    response.qcontext['parent_master'] = parent_slide.channel_id
        return response



class AcademyController(http.Controller):
    
    @http.route('/academy/delivery/upload', type='http', auth="user", methods=['POST'], website=True)
    def academy_upload_delivery(self, slide_id, file, fullscreen=False, **kwargs):
        slide = request.env['slide.slide'].browse(int(slide_id))
        if not slide.exists() or slide.slide_category != 'delivery':
            return request.redirect('/slides')
            
        # Check membership
        if not slide.channel_id.is_member:
            return request.redirect(slide.website_url)

        # Get or create slide.slide.partner relation
        slide_partner = request.env['slide.slide.partner'].sudo().search([
            ('slide_id', '=', slide.id),
            ('partner_id', '=', request.env.user.partner_id.id)
        ], limit=1)
        
        if not slide_partner:
            # Should exist if member, but safety check
            # SECURITY: Enforcing creation for current user only prevents IDOR
            slide_partner = request.env['slide.slide.partner'].sudo().create({
                'slide_id': slide.id,
                'channel_id': slide.channel_id.id,
                'partner_id': request.env.user.partner_id.id
            })

        # Save file
        # Check upload limit
        limit_mb = slide.channel_id.upload_size_limit
        if limit_mb > 0:
            # Approximate size check (not perfect for base64 but good enough before processing)
            # file.content_length is usually available in Werkzeug requests
            content_length = request.httprequest.content_length
            if content_length and content_length > (limit_mb * 1024 * 1024):
                 return request.render('website_slides.course_slides_list', {
                    'channel': slide.channel_id,
                    'error_msg': f"El archivo excede el límite de {limit_mb} MB."
                 }) # Ideally show a nice error, but this is a basic guard
        
        file_content = base64.b64encode(file.read())
        # Re-check actual binary size if content_length header was missing or faked
        if limit_mb > 0 and (len(file_content) * 0.75) > (limit_mb * 1024 * 1024):
             return request.redirect(slide.website_url + '?error=size_limit')

        filename = file.filename
        
        slide_partner.sudo().write({
            'delivery_file': file_content,
            'delivery_filename': filename,
            'delivery_date': fields.Datetime.now(),
            'status': 'submitted',
            'completed': True
        })
        
        # Determine redirect URL (stay on slide page)
        redirect_url = f'/slides/slide/{slide.id}'
        if fullscreen:
            redirect_url += '?fullscreen=1'
        return request.redirect(redirect_url)
