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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('certification'):
                self._check_certification_permission()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('certification'):
            self._check_certification_permission()
        return super().write(vals)

    def _check_certification_permission(self):
        """ Impide que los docentes creen certificaciones (Solo Admins/Directores) """
        user = self.env.user
        if user.has_group('elearning_universidad.grupo_personal_docente') and \
           not user.has_group('elearning_universidad.grupo_director_academico') and \
           not user.has_group('elearning_universidad.grupo_administrador_universidad'):
            raise ValidationError("Solo los Directores Académicos o Administradores pueden crear Certificaciones.")

    # --- Ayuda para Dominios XML ---
    is_university_admin = fields.Boolean(
        string='Es Admin Universidad', 
        compute='_compute_is_university_admin', 
        search='_search_is_university_admin'
    )

    def _compute_is_university_admin(self):
        is_admin = self.env.user.has_group('elearning_universidad.grupo_administrador_universidad')
        for record in self:
            record.is_university_admin = is_admin

    def _search_is_university_admin(self, operator, value):
        if self.env.user.has_group('elearning_universidad.grupo_administrador_universidad'):
            return [(1, '=', 1)] # Mostrar todo si es admin
        return [(0, '=', 1)] # No mostrar nada extra si no es admin (se aplican el resto de filtros)
