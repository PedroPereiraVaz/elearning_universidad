from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Survey(models.Model):
    _inherit = 'survey.survey'

    is_exam = fields.Boolean(
        string="Es un Examen",
        copy=False,
        help="Indica que esta encuesta funciona como un Examen Universitario vinculante."
    )

    @api.onchange('is_exam')
    def _onchange_is_exam(self):
        if self.is_exam:
            self.certification = False
            self.scoring_type = 'scoring_with_answers'
            self.access_mode = 'token'
            self.users_login_required = True
            self.is_attempts_limited = True
            self.is_time_limited = True

    @api.constrains('is_exam', 'scoring_type')
    def _check_exam_scoring(self):
        for record in self:
            if record.is_exam and record.scoring_type == 'no_scoring':
                raise ValidationError("Un Examen Universitario no puede tener la opción 'Sin Puntuación'. Debe seleccionar un tipo de puntuación.")

    @api.onchange('scoring_type')
    def _onchange_scoring_type_exam(self):
        if self.is_exam and self.scoring_type == 'no_scoring':
            self.scoring_type = 'scoring_with_answers'
            return {'warning': {'title': 'Opción no válida', 'message': 'Los exámenes universitarios deben tener puntuación obligatoriamente.'}}
