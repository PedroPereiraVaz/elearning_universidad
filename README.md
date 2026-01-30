# 🎓 Universidad eLearning - Gestión de Cursos (Odoo 18)

![Odoo Version](https://img.shields.io/badge/Odoo-18.0-714B67?logo=odoo&logoColor=white)
![Category](https://img.shields.io/badge/Category-Website%2FeLearning-blue)
![License](https://img.shields.io/badge/License-LGPL--3-green)

Módulo avanzado de personalización para el núcleo de **eLearning (Website Slides)** de Odoo, diseñado específicamente para entornos universitarios que requieren una jerarquía compleja de cursos, sistemas de calificación ponderados y flujos de aprobación académica.

---

## 🏛️ Propósito del Módulo

Este módulo extiende la funcionalidad estándar de Odoo para permitir la gestión de una estructura académica tripartita:

1.  **Masters**: Entidades principales que agrupan múltiples asignaturas.
2.  **Asignaturas**: Unidades de aprendizaje independientes vinculadas a un Master.
3.  **Microcredenciales**: Cursos independientes o especializados.

---

## 🚀 Características Principales

- **Jerarquía de Cursos**: Vinculación lógica entre Masters y Asignaturas mediante un sistema de sincronización automática.
- **Sistema de Calificación (Gradebook)**:
  - Cálculo automático de notas finales basado en pesos configurables.
  - Soporte para entregables evaluables y no evaluables.
- **Gestión Académica**:
  - Estados de aprobación (Borrador, Pendiente de Aprobación, Publicado, Rechazado).
  - Wizards para rechazo con retroalimentación y programación de publicaciones.
- **Seguridad y Roles**:
  - Director Académico (Control total).
  - Docente de Universidad (Gestión de sus propios cursos).
  - Administrador de Universidad.
- **Portal del Estudiante**: Interfaz mejorada para visualizar calificaciones y progreso.

---

## 🛠️ Requisitos e Instalación

### Dependencias

- `website_slides` (eLearning base)
- `survey` (Para exámenes y encuestas)
- `website_slides_survey`
- `website_sale_slides` (Venta de cursos)

---

## 📋 Inventario del Módulo (Developer Focus)

| Directorio / Archivo               | Función / Responsabilidad                                                                             |
| :--------------------------------- | :---------------------------------------------------------------------------------------------------- |
| **`models/`**                      | **Núcleo Lógico**                                                                                     |
| `slide_channel.py`                 | Extensión principal de cursos. Gestiona la jerarquía Master/Asignatura y flujos de aprobación.        |
| `slide_gradebook.py`               | Lógica de cálculo de notas, estados de titulación y sincronización de actas.                          |
| `slide_slide.py`                   | Extensión de contenidos (documentos, videos). Añade flags de "evaluable" y sincronización con Slides. |
| `survey_survey.py`                 | Adaptaciones para exámenes universitarios.                                                            |
| **`views/`**                       | **Interfaces**                                                                                        |
| `slide_channel_views.xml`          | Formularios extendidos para cursos (Masters y Microcredenciales).                                     |
| `slide_gradebook_views.xml`        | Vistas dedicadas para la gestión de actas y calificaciones.                                           |
| `universidad_menu_views.xml`       | Reestructuración total del menú de eLearning para adaptarlo al flujo universitario.                   |
| `portal_templates.xml`             | Modificaciones a la vista del portal del estudiante (Mis Cursos).                                     |
| **`wizard/`**                      | **Acciones Rápidas**                                                                                  |
| `slide_channel_reject_wizard.py`   | Asistente para que directores rechacen cursos con un motivo específico.                               |
| `slide_channel_schedule_wizard.py` | Orquestador para programar la publicación de contenidos.                                              |
| **`security/`**                    | **Permisos y Reglas**                                                                                 |
| `security.xml`                     | Definición de Grupos de Usuario.                                                                      |
| `ir_rule.xml`                      | Reglas de registro.                                                                                   |

---

## ⚠️ Instrucciones Críticas de Mantenimiento

### Desinstalación y Recuperación de Vistas

> [!WARNING]
> **COMPORTAMIENTO CRÍTICO DETECTADO:**
> Este módulo modifica profundamente la interfaz de carga de Odoo y desactiva ciertos menús nativos de `website_slides` para limpiar la UI académica.
>
> **Si desinstalas este módulo**, es posible que el menú de eLearning en el backend o frontend no se visualice correctamente debido a las herencias de vistas.
>
> **Para restaurar la funcionalidad nativa tras desinstalar:**
> Debes actualizar el módulo base de eLearning mediante terminal para forzar la regeneración de los assets y vistas nativas:
>
> ```bash
> python odoo-bin -u website_slides -d TU_BASE_DE_DATOS
> ```

---

## 🔧 Datos del Desarrollador

- **Autor**: Pedro Pereira
- **Versión Técnico**: `18.0.1.0.0`
- **Licencia**: LGPL-3

---

_Este documento ha sido generado para facilitar el onboarding de nuevos desarrolladores al ecosistema de la Universidad._
