{
    'name': 'Universidad eLearning - Gestión de Cursos',
    'version': '18.0.1.0.0',
    'category': 'Website/eLearning',
    'summary': 'Gestión de Microcredenciales, Masters y Asignaturas',
    'description': """
        Módulo avanzado para la gestión universitaria que incluye:
        - Jerarquía de cursos (Masters, Asignaturas, Microcredenciales).
        - Sistema de calificación manual y ponderada.
        - Emisión de títulos asíncrona.
        - Publicación programada de contenidos.
        - Aislamiento de seguridad por roles (Director, Docente).
    """,
    'author': 'Pedro Pereira',
    'depends': ['website_slides', 'survey', 'website_slides_survey', 'website_sale_slides'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'wizard/slide_channel_reject_views.xml',
        'wizard/slide_channel_schedule_views.xml',
        'views/slide_channel_views.xml',
        'views/slide_slide_views.xml',
        'views/slide_gradebook_views.xml',
        'views/survey_survey_views.xml',
        'views/universidad_menu_views.xml',
        'views/website_slides_templates.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}