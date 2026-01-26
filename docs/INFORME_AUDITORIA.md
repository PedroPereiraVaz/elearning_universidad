# Informe de Auditoría Odoo 18 - Universidad eLearning

**Fecha:** 26 de Enero de 2026
**Módulo Auditado:** `elearning_universidad` (Versión 18.0.1.0.0)
**Auditor:** Antigravity (AI Agent)

---

## 1. Resumen Ejecutivo

| Estado General     | **AMARILLO / ANARANJADO**                                                                                                                     |
| :----------------- | :-------------------------------------------------------------------------------------------------------------------------------------------- |
| **Estabilidad**    | **Riesgo Medio**. Hay lógica recursiva peligrosa en la sincronización Master-Asignatura que podría romper el servidor en operaciones masivas. |
| **Seguridad**      | **Riesgo Bajo**. Las reglas son estrictas (paranoicas), lo cual es bueno, pero están implementadas de forma ineficiente.                      |
| **Mantenibilidad** | **Riesgo Alto**. Excesiva lógica hardcoded en Vistas XML y "Actions Server" para gestionar la UI, dificultando actualizaciones futuras.       |
| **Performance**    | **Riesgo Medio**. Reglas de registro (Record Rules) usan `JOINs` implicitos complejos en lugar de usar los campos optimizados ya calculados.  |

**Conclusión Principal:**  
El módulo es funcional y tiene una arquitectura de negocio sólida conceptualmente, pero técnicamente sufre de "sobre-ingeniería" en la capa de Vistas y "sub-ingeniería" en la capa de Modelos (fata de optimización). Se ha intentado resolver problemas de permisos ocultando botones mediante XML en lugar de confiar en el ORM.

---

## 2. Análisis de Integridad Estructural

- **Organización:** Correcta. Separación clara de models, views, security, wizard.
- **Manifest:** Correcto. El orden de carga en `data` es lógico (seguridad -> datos -> wizards -> vistas -> menús).
- **Archivos Huérfanos/Suspechosos:**
  - `controllers/academy_controller.py.old`: **Código Muerto**. Debe eliminarse. Git es para historial, no el sistema de archivos.
  - `controllers/main.py`: Gestión manual de subida de archivos (Base64) en lugar de usar `ir.attachment` nativo de Odoo. Esto inflará la base de datos innecesariamente.

---

## 3. Análisis Archivo por Archivo

### `models/slide_channel.py` (Núcleo)

- **Propósito:** Extiende el modelo de cursos para añadir lógica universitaria (Master/Asignatura).
- **Problemas Críticos:**
  - **Redundancia de Seguridad:** El método `_compute_security_fields` (Líneas 49-70) calcula booleanos (`can_manage_config`, etc.) para controlar la UI. Sin embargo, luego en el método `write` (Líneas 531-620) se vuelve a calcular manualmente si es admin o director. **Solución:** Centralizar la lógica de permisos en un método o usar el compute field dentro del write si es `store=False`.
  - **Hardcoding:** Los tipos de curso (`asignatura`, `master`) están "quemados" en el código. Si mañana se crea "Doctorado", hay que tocar código Python y XML.
  - **Riesgo de Recursión:** La función `_sincronizar_slide_master` (Línea 199) y su contraparte en `slide.slide` intentan mantenerse sincronizadas mutuamente. Aunque hay banderas de contexto (`mail_notrack`), es frágil.
  - **Lógica Incompleta:** `_sincronizar_producto_universidad` (Línea 182) solo actúa si `enroll == 'payment'`. Si un curso pasa de pago a gratuito, el producto queda "vivo".

### `models/slide_slide.py` (Contenido)

- **Propósito:** Gestiona los contenidos. Parches para exámenes y asignatura-como-contenido.
- **Mejoras Nativas Odoo 18:**
  - **Hack de Vistas (`get_view`, `fields_get`):** (Líneas 56-82). Se intenta ocultar la opción 'Asignatura' del selector de tipos manipulando la definición de la vista en tiempo real. **Code Smell.** Esto es frágil ante actualizaciones de Odoo. Debería manejarse con `domain` en la vista XML o Action.
  - **Bidireccionalidad Peligrosa:** `_sincronizar_asignatura_master` (Línea 248) escribe en la asignatura cuando se toca el slide. Esto crea un acoplamiento fuerte que dispara múltiples escrituras en BD por una sola acción de usuario.

### `models/slide_gradebook.py` (Notas)

- **Propósito:** Calificaciones.
- **Problemas:**
  - **N+1 Query:** En `_compute_nota_academica` (Línea 162), para cada alumno en un Master, se itera sobre sus asignaturas y **dentro del bucle** se hace un `search` (`slide.channel.partner`). Si tienes 100 alumnos y 10 asignaturas, son 1000 consultas SQL. **CRÍTICO para performance.**
  - **Duplicidad:** La lógica de ponderación repite cálculos que podrían estar almacenados.

### `views/slide_channel_views.xml` (UI Cursos)

- **Propósito:** Vista principal del curso.
- **Problemas:**
  - **Abuso de `xpath`:** Hay más de 20 inyecciones xpath. Esto hace que la vista sea muy propensa a romperse si Odoo cambia un ID en una actualización menor.
  - **Seguridad por Ocultación:** Se usa `invisible="..."` masivamente para "proteger" campos. Un usuario astuto podría reactivarlos desde el navegador y editar si el python no protege bien (aunque en este caso el Python sí protege, hace que el XML sea ilegible).
  - **Grupos Hardcoded:** Se repite `groups="elearning_universidad.grupo_..."` docenas de veces. Debería inyectarse el grupo en la vista raíz o usar herencia de vista específica por grupo si es muy diferente.

### `views/universidad_menu_views.xml` (Menús)

- **Propósito:** Árbol de menús y Dispatchers.
- **Hallazgo Importante (Deuda Técnica):**
  - **Dispatchers (`action_server_...`):** (Líneas 78-196). Se usa código Python dentro del XML para decidir qué vista mostrar según el grupo del usuario.
  - _Por qué está mal:_ Odoo tiene mecanismos nativos para esto (Action Window con `groups_id` en los menús, o Record Rules que filtran los datos naturalmente).
  - _Consecuencia:_ Si añades un nuevo rol, tienes que modificar código Python incrustado en XML.

### `security/security.xml` (Reglas)

- **Propósito:** ACLs y Record Rules.
- **Oportunidad Perdida:**
  - En `slide_channel.py` (Línea 151) existe el campo: `all_personal_docente_ids` (Many2many computado y almacenado).
  - Sin embargo, las reglas de registro (Líneas 50-70) **NO LO USAN**. Siguen haciendo `channel_id.master_id.personal_docente_ids`.
  - **Impacto:** Odoo tiene que hacer JOINS de 3 niveles en cada lectura de base de datos. Usar el campo plano `all_personal_docente_ids` aceleraría la lectura drásticamente.

---

## 4. Análisis Transversal (Relaciones)

1.  **Disonancia Seguridad-Vista:** La seguridad real está en Python (`write`), pero la vista intenta replicarla con `invisible`. Cuando la lógica cambia en Python, la vista queda desincronizada (botones visibles que dan error al clicar).
2.  **Sincronización Master-Asignatura:** El sistema intenta mantener dos objetos distintos (el Curso 'Asignatura' y el Slide 'Contenido del Master') idénticos en nombre y estado.
    - _Problema:_ Es una duplicación de datos conceptual.
    - _Recomendación:_ Evaluar si la Asignatura _debe_ ser un curso separado o si el Master debería ser simplemente una agrupación lógica (Track/Tag) en lugar de un curso contenedor físico. (Asumiendo que el diseño actual es requisito del cliente, se debe robustecer la sincronización).

---

## 5. Lista de Acciones Recomendadas (Priorizadas)

### [CRÍTICO] - Estabilidad y Performance

1.  **Optimizar Record Rules:** Modificar `security/security.xml` para que usen el campo calculado `all_personal_docente_ids` en lugar de navegar por relaciones (Master -> Asignatura -> Docentes).
2.  **Arreglar N+1 en Gradebook:** Reescribir `_compute_nota_academica` en `slide_gradebook.py` para hacer una sola búsqueda `read_group` o búsqueda optimizada fuera del bucle `for asig in asignaturas`.
3.  **Proteger Recursión:** Crear un decorador o context manager explícito `with env.context(syncing_master=True):` para envolver todas las llamadas de sincronización entre Slide y Asignatura, garantizando que no se llamen mutuamente en bucle.

### [ALTO] - Limpieza y Seguridad

4.  **Eliminar Dispatchers de Menú:** Reemplazar las Acciones de Servidor en `universidad_menu_views.xml` por Acciones de Ventana estándar con dominios predefinidos. Dejar que las Record Rules filtren lo que el usuario ve. Si el usuario no debe ver el menú de "Configuración", ocultar el menú con `groups=`, no con código Python.
5.  **Refactorizar Permisos UI:** En `slide_channel_views.xml`, en lugar de repetir `groups="..."` en cada botón, usar el campo calculado `can_manage_config` (que ya existe) para controlar la visibilidad (`invisible="not can_manage_config"`). Esto centraliza la lógica en Python.

### [MEDIO] - Deuda Técnica y Buenas Prácticas

6.  **Estandarizar Subida de Archivos:** Modificar el controlador `main.py` y el modelo `slide_gradebook.py` para usar `ir.attachment`. Eliminar el campo `archivo_entrega` (Binary) y usar una relación Many2many con `ir.attachment`.
7.  **Limpieza:** Eliminar `controllers/academy_controller.py.old`.
8.  **Eliminar Hack de Vistas (`get_view`):** Usar dominios en la acción de ventana o atributos `context` para filtrar los tipos de slide permitidos, en lugar de inyectar código en `get_view`.

---

**Siguiente Paso Sugerido:** Proceder con las acciones [CRÍTICO] y [ALTO] creando una rama de refactorización (`refactor/security_performance`).
