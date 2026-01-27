from odoo import models, fields

class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    def write(self, vals):
        """ 
        Sincronización Inmediata con el Boletín de Notas (Gradebook).
        Cuando el examen finaliza (state -> done), empujamos la nota y estado.
        """
        res = super(SurveyUserInput, self).write(vals)
        
        if 'state' in vals and vals['state'] == 'done':
            for user_input in self:
                # Verificar si está vinculado a un curso (slide.slide.partner)
                if user_input.slide_partner_id:
                    # Cálculo de Nota (0-10)
                    nota_obtenida = (user_input.scoring_percentage / 100.0) * 10
                    
                    # Actualización del registro académico
                    # Usamos sudo por si el alumno no tiene permisos de escritura en su propio registro (seguridad)
                    user_input.slide_partner_id.sudo().write({
                        'nota_evaluacion': nota_obtenida,
                        'estado_evaluacion': 'evaluado',
                        'fecha_entrega': fields.Datetime.now()
                    })
        return res

    def _check_for_failed_attempt(self):
        """ 
        OVERRIDE UNIVERSIDAD:
        Odoo por defecto des-matricula al usuario del curso si falla la certificación
        y no le quedan intentos (lógica de venta de certificados).
        
        En la Universidad, suspender un examen NO implica ser expulsado de la asignatura.
        Simplemente se registra la nota (fallo) y el alumno mantiene acceso a los contenidos para estudiar.
        
        Anulamos este método para evitar el unlink del slide.channel.partner.
        """
        pass
