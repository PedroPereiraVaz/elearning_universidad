# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SlideChannelScheduleWizard(models.TransientModel):
    _name = 'slide.channel.schedule.wizard'
    _description = 'Wizard para programar la publicación de un curso'

    channel_id = fields.Many2one('slide.channel', string='Curso', required=True)
    fecha_publicacion = fields.Datetime(
        string='Fecha de Publicación', 
        required=True, 
        default=fields.Datetime.now,
        help="El curso se publicará automáticamente en esta fecha a través del CRON universitario."
    )

    @api.constrains('fecha_publicacion')
    def _check_fecha(self):
        for record in self:
            if record.fecha_publicacion < fields.Datetime.now():
                raise ValidationError("La fecha de publicación no puede ser anterior al momento actual.")

    def action_confirm_schedule(self):
        self.ensure_one()
        # Llamamos al método del canal con la fecha capturada
        return self.channel_id.action_programar(self.fecha_publicacion)
