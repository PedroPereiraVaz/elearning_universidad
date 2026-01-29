# Inventario de Funciones en `models/slide_channel.py`

Este documento detalla todas las funciones encontradas en el archivo `models/slide_channel.py`, línea por línea.

**Nota:** Se han detectado múltiples definiciones para las funciones `create`, `write` y `_sync_course_product`. Odoo/Python utilizará la _última_ definición encontrada en el archivo, lo que anula las definiciones anteriores.

## Funciones

### `_search_get_detail(self, website, order, options)`

- **Ubicación:** Línea 18
- **Descripción:** Sobrescribe el método de búsqueda global del sitio web (website_slides).
- **Acciones:**
  - Filtra los resultados para excluir cursos de tipo 'asignatura'.
  - Filtra los resultados para excluir cursos que no estén en estado 'publicado' (estado_universidad).

### `_compute_security_fields(self)`

- **Ubicación:** Línea 90
- **Descripción:** Calcula campos booleanos de permisos y seguridad para la interfaz de usuario.
- **Acciones:**
  - Determina si el usuario actual es Admin, Director Académico o Docente.
  - Asigna `can_manage_config`: Permiso para editar configuración (Nombre, Opciones).
  - Asigna `can_see_financials`: Permiso para ver precios y ventas.
  - Asigna `can_manage_members`: Permiso para invitar o ver miembros.
  - Asigna `is_university_admin` y `is_exclusive_teacher` para lógica de vista.

### `_compute_can_upload(self)`

- **Ubicación:** Línea 134
- **Descripción:** Controla permisos de subida de contenido.
- **Acciones:**
  - Extiende el método base.
  - Autoritza explícitamente a: Directores Académicos asignados, Personal Docente asignado y Administradores de Universidad.

### `_compute_can_publish(self)`

- **Ubicación:** Línea 149
- **Descripción:** Controla permisos de publicación de contenido.
- **Acciones:**
  - Extiende el método base.
  - Autoritza a Directores, Docentes asignados y Administradores.

### `_get_plantillas_titulo(self)`

- **Ubicación:** Línea 234
- **Descripción:** Provee las opciones para el campo de selección de plantilla de título.
- **Acciones:**
  - Intenta obtener la selección del modelo `survey.survey`.
  - Si falla, devuelve una lista predeterminada (modern_gold, modern_purple, classic_blue).

### `_compute_all_personal_docente_ids(self)`

- **Ubicación:** Línea 260
- **Descripción:** Calcula la lista completa de docentes vinculados (herencia).
- **Acciones:**
  - Combina los docentes directos con los heredados.
  - Si es Master: incluye docentes de sus asignaturas.
  - Si es Asignatura: incluye docentes del Master padre.

### `_compute_duracion_horas(self)`

- **Ubicación:** Línea 275
- **Descripción:** Calcula la duración total del curso.
- **Acciones:**
  - Master: Suma `duracion_horas` de sus asignaturas.
  - Microcredencial: Suma `completion_time` de sus slides (contenidos).
  - Asignatura: Mantiene el valor manual.

### `_sincronizar_producto_universidad(self)`

- **Ubicación:** Línea 284
- **Advertencia:** Redefinido/Sobrescrito en la línea 916.
- **Descripción:** Vincula el curso con un producto de Odoo para ventas.
- **Acciones:**
  - Crea o actualiza un `product.product` si el curso es de pago.
  - Archiva el producto si el curso pasa a ser gratuito.

### `_sincronizar_slide_master(self)`

- **Ubicación:** Línea 304
- **Descripción:** Representa la Asignatura como un contenido (Slide) dentro del Master.
- **Acciones:**
  - Busca o crea un registro `slide.slide` en el Master vinculado.
  - Copia nombre y visibilidad de la asignatura al slide.
  - Usa flags de contexto (`avoid_recursive_sync`) para evitar bucles infinitos.
  - Elimina slides huérfanos si la asignatura cambia de Master.

### `action_open_add_asignatura(self)`

- **Ubicación:** Línea 354
- **Descripción:** Acción para botón 'Agregar Asignatura'.
- **Acciones:**
  - Abre el formulario de creación de `slide.slide` (contenido) preconfigurado como 'sub_course' (Asignatura).
  - Permite crear asignaturas desde la vista del Master.

### `_format_notification_html(self, titulo, mensaje, tipo='info')`

- **Ubicación:** Línea 381
- **Descripción:** Helper para formatear mensajes del chatter.
- **Acciones:**
  - Genera código HTML con estilos y colores según el tipo (success, warning, danger, etc.).

### `_notificar_administradores(self, titulo, mensaje, tipo='info')`

- **Ubicación:** Línea 421
- **Descripción:** Envía notificaciones al grupo de Administradores.
- **Acciones:**
  - Busca usuarios en el grupo `grupo_administrador_universidad`.
  - Publica un mensaje (`message_post`) dirigido a ellos.

### `_sincronizar_seguidores_staff(self)`

- **Ubicación:** Línea 435
- **Descripción:** Gestiona suscripciones al chatter.
- **Acciones:**
  - Añade a Directores Académicos y Personal Docente como seguidores del curso.

### `_check_requisitos_publicacion(self)`

- **Ubicación:** Línea 448
- **Descripción:** Valida condiciones antes de publicar/programar.
- **Acciones:**
  - Verifica presencia de Director Académico (en Master/Microcredencial).
  - Verifica vinculación a Master y Director (en Asignatura).
  - Verifica precio > 0 si es de pago.
  - Verifica plantilla de título si emite título.
  - Verifica duración > 0.

### `_onchange_master_id_directores(self)`

- **Ubicación:** Línea 483
- **Descripción:** Automatismo al cambiar el Master.
- **Acciones:**
  - Copia los directores del Master a la Asignatura.

### `action_presentar(self)`

- **Ubicación:** Línea 488
- **Descripción:** Avanza estado a 'Presentado'.
- **Acciones:**
  - Valida asignación de director.
  - Notifica a administradores.

### `action_rechazar(self, motivo)`

- **Ubicación:** Línea 503
- **Descripción:** Avanza estado a 'Rechazado'.
- **Acciones:**
  - Solo admins.
  - Guarda motivo y notifica en rojo.

### `action_subsanar(self)`

- **Ubicación:** Línea 519
- **Descripción:** Reactiva un curso rechazado ('Subsanación').
- **Acciones:**
  - Notifica a administradores.

### `action_confirmar_programacion(self)`

- **Ubicación:** Línea 531
- **Descripción:** Confirma fecha programada.
- **Acciones:**
  - Llama a `action_programar`.

### `action_programar(self, fecha)`

- **Ubicación:** Línea 538
- **Descripción:** Establece estado 'Programado'.
- **Acciones:**
  - Guarda fecha de publicación.
  - Notifica programación.

### `action_publicar(self)`

- **Ubicación:** Línea 555
- **Descripción:** Publica el curso.
- **Acciones:**
  - Valida permisos (Admin/Director según caso).
  - Establece `estado_universidad='publicado'` e `is_published=True`.
  - Notifica éxito.

### `action_finalizar(self)`

- **Ubicación:** Línea 581
- **Descripción:** Finaliza y archiva el curso.
- **Acciones:**
  - Establece estado 'finalizado' y `active=False`.
  - Aplica en cascada a asignaturas si es Master.

### `create(self, vals_list)` (Primera definición)

- **Ubicación:** Línea 613
- **Advertencia:** Esta función está redefinida en la línea 872. El código de la línea 613 **NO** se ejecutará.
- **Descripción (Código inactivo):** Implementaba validaciones estrictas de creación y defaults para asignaturas.

### `_onchange_enroll_payment(self)`

- **Ubicación:** Línea 659
- **Descripción:** Validación UI para cursos de pago.
- **Acciones:**
  - Exige nombre antes de marcar como pago.

### `_onchange_tipo_curso_universidad(self)`

- **Ubicación:** Línea 672
- **Descripción:** Defaults UI al seleccionar 'Asignatura'.
- **Acciones:**
  - Configura enroll='invite', visibility='members', precio=0.

### `write(self, vals)` (Primera definición)

- **Ubicación:** Línea 680
- **Advertencia:** Esta función está redefinida en la línea 886. El código de la línea 680 **NO** se ejecutará completamente (la definición posterior la olvida).
- **Descripción (Código inactivo):** Contenía lógica de bloqueo de campos inmutables y permisos de edición granulares.

### `unlink(self)`

- **Ubicación:** Línea 771
- **Descripción:** Borrado de registros.
- **Acciones:**
  - Solo permite a admins borrar.
  - Limpia slides vinculados antes de borrar.

### `_cron_publicar_cursos_programados(self)`

- **Ubicación:** Línea 791
- **Descripción:** Tarea programada (Cron).
- **Acciones:**
  - Busca cursos programados vencidos y llama a `action_publicar`.

### `_action_add_members(self, target_partners, **kwargs)`

- **Ubicación:** Línea 803
- **Descripción:** Al añadir miembros/alumnos.
- **Acciones:**
  - Asegura registros de seguimiento en slides evaluables.
  - Si es Master, añade los miembros a las asignaturas (recursión).

### `_remove_membership(self, partner_ids)`

- **Ubicación:** Línea 818
- **Descripción:** Al quitar miembros.
- **Acciones:**
  - Si es Master, quita los miembros de las asignaturas.

### `_verificar_jerarquia(self)`

- **Ubicación:** Línea 828
- **Descripción:** Validación de consistencia estructura.
- **Acciones:**
  - Asignatura solo en Master.
  - Master no en otro curso.
  - Microcredencial aislada.

### `action_view_gradebook_students(self)`

- **Ubicación:** Línea 849
- **Descripción:** Abre lista de alumnos para Gradebook.
- **Acciones:**
  - Retorna acción de ventana filtrada por el curso.

---

### SECCIÓN DE REDEFINICIONES (Código Activo Actual)

Las siguientes funciones aparecen al final del archivo y **sobrescriben** a sus homólogas anteriores.

### `create(self, vals_list)` (Segunda definición - ACTIVA)

- **Ubicación:** Línea 872
- **Descripción:** Creación de registros.
- **Acciones:**
  - Llama a `super()`.
  - Sincroniza seguidores (docentes/directores).
  - Sincroniza producto si es de pago.
  - **Diferencia:** No incluye las restricciones de permisos y defaults de la primera definición.

### `write(self, vals)` (Segunda definición - ACTIVA)

- **Ubicación:** Línea 886
- **Descripción:** Escritura de registros.
- **Acciones:**
  - Detecta cambios en staff para actualizar suscriptores.
  - Llama a `super()`.
  - Sync Producto.
  - **Diferencia:** No incluye los bloqueos de seguridad y validaciones de estado de la primera definición.

### `_sync_course_product(self)` (Segunda definición - ACTIVA)

- **Ubicación:** Línea 916
- **Descripción:** Sincronización con producto.
- **Acciones:**
  - Crea o actualiza producto con `sudo()`.
  - Similar a la anterior pero usa `invoice_policy='order'`.

### `_check_paid_course_integrity(self)`

- **Ubicación:** Línea 952
- **Descripción:** Placeholder para integridad.
- **Acciones:** `pass` (No hace nada).

### `action_channel_invite(self)`

- **Ubicación:** Línea 960
- **Descripción:** Acción de invitar usuarios.
- **Acciones:**
  - Bloquea la acción si el curso es de pago.
