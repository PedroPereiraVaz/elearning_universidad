# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SlideChannelRejectWizard(models.TransientModel):
    _name = 'slide.channel.reject.wizard'
    _description = 'Wizard para rechazar curso con motivo'

    channel_id = fields.Many2one('slide.channel', string='Curso', required=True)
    motivo = fields.Text(string='Motivo de Rechazo', required=True)

    def action_confirm_rejection(self):
        self.ensure_one()
        # Llamamos al método del canal con el motivo capturado
        return self.channel_id.action_rechazar(self.motivo)
