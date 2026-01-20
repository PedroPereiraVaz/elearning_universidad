{
    'name': 'Odoo Academy & Masters Extension',
    'version': '18.0.1.0.1',
    'category': 'Website/eLearning',
    'summary': 'Advanced Academic Management: Masters, Grading, and Roles',
    'description': """
        Extends Odoo eLearning to support:
        - Master Programs (Courses of Courses)
        - Academic Subjects (Asignaturas)
        - Weighted Grading System (0-10)
        - Manual Deliverables (Entregables)
        - Advanced Roles (Academy Director, Multi-Teacher)
        - Manual Certification Approval
    """,
    'author': 'Pedro Pereira',
    'depends': ['website_slides', 'product', 'website_sale_slides', 'survey'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/slide_channel_views.xml',
        'views/slide_slide_views.xml',
        'views/slide_channel_partner_views.xml',
        'views/website_slides_templates.xml',
        'views/website_academy_templates.xml',
        'views/academy_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
