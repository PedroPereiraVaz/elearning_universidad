# Modelo de Datos - Universidad eLearning

Este documento describe las extensiones de los modelos de Odoo realizadas para soportar el flujo académico universitario.

## 1. Canal de eLearning (`slide.channel`)

El modelo base se ha extendido para soportar la jerarquía de cursos y el flujo de estados de la universidad.

### Campos Principales

- **`tipo_curso`**: Selección entre `Master`, `Microcredencial` o `Asignatura`.
- **`estado_universidad`**: Controla el ciclo de vida del curso:
  - `Borrador`: Estado inicial.
  - `Presentado`: Enviado por el Director Académico para revisión.
  - `Rechazado`: Devuelto por el Administrador con motivos técnicos/académicos.
  - `Subsanación`: Estado intermedio para correcciones.
  - `Programado`: Aprobado y en espera de su fecha de publicación.
  - `Publicado`: Disponible en el portal.
- **`director_academico_ids`**: Relación con usuarios que tienen el rol de Director.
- **`personal_docente_ids`**: Relación con usuarios que imparten la asignatura.
- **`master_id` / `asignatura_ids`**: Campos para la relación jerárquica Master-Asignatura.

### Lógica de Negocio

- **Cálculo de Duración**: Los Masters suman automáticamente las horas de sus asignaturas. Las Microcredenciales suman el tiempo de sus contenidos.
- **Sincronización de Productos**: Los cursos de tipo 'pago' crean/actualizan automáticamente un producto en Odoo.
- **Propagación de Matrícula**: Al inscribir a un alumno en un Master, se le inscribe automáticamente en todas sus asignaturas constituyentes.

---

## 2. Contenidos (`slide.slide`)

Se han añadido propiedades para gestionar la evaluación y la vinculación con asignaturas.

### Campos Clave

- **`es_evaluable`**: Indica si el contenido requiere una nota manual (ej. Entregables).
- **`asignatura_id`**: En un Master, este campo vincula un slide con el curso de asignatura real.
- **`fecha_programada`**: Fecha para la publicación automática vía CRON.
- **Categorías Universitarias**: Se han añadido `sub_course` (Asignatura) y `delivery` (Entregable).
- **Campos Estadísticos (Técnicos)**: `nbr_sub_course` y `nbr_delivery`. Estos campos son obligatorios para evitar errores de clave (`KeyError`) en el motor de estadísticas nativo de Odoo al extender los tipos de contenido.

### Lógica Destacada

- **Redirección Fluida**: Al acceder a una asignatura desde el Master, el sistema redirige automáticamente al primer contenido disponible de la asignatura.
- **Bloqueo de Autocompletado**: Los contenidos 'evaluables' no se marcan como completados por simple visita; requieren acción explícita.

---

## 3. Seguimiento y Calificaciones (`slide.slide.partner` / `slide.channel.partner`)

### Evaluaciones de Contenido (`slide.slide.partner`)

- **`nota_evaluacion`**: Calificación de 0 a 10.
- **`estado_evaluacion`**: Flujo: `Pendiente Presentar` -> `Pendiente Revisión` -> `Evaluado`.
- **Gestión de Archivos**: Almacena el `archivo_entrega` del alumno.

### Boletín Académico (`slide.channel.partner`)

- **`nota_final`**:
  - Para **Asignaturas**: Promedio simple de sus contenidos evaluables.
  - Para **Masters**: Promedio ponderado por la duración (horas) de sus asignaturas.
- **`estado_nota`**: Gestiona el acta hasta la emisión del título (`Pendiente Certificar` -> `Certificado`).
