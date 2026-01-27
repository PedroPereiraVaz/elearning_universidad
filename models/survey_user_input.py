from odoo import models

class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

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
