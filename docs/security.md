# Seguridad y Roles (`security`)

La seguridad del módulo se basa en un aislamiento estricto entre el personal docente y la administración de la universidad.

## 1. Grupos de Usuario

Se han definido tres niveles de acceso jerárquicos:

| Rol                           | Descripción                               | Permisos Clave                                                       |
| :---------------------------- | :---------------------------------------- | :------------------------------------------------------------------- |
| **Personal Docente**          | Profesores de asignaturas.                | Gestionar contenidos y calificar alumnos en SUS asignaturas.         |
| **Director Académico**        | Responsable de Masters/Microcredenciales. | Configurar la estructura académica y presentar cursos para revisión. |
| **Administrador Universidad** | Superusuario académico.                   | Aprobar, rechazar, programar o publicar cualquier curso.             |

---

## 2. Reglas de Registro (Aislamiento de Datos)

Para asegurar que un profesor no vea datos de otros cursos, se aplican las siguientes reglas:

- **Propiedad de Cursos**: Los Docentes y Directores solo pueden ver los cursos donde están explícitamente asignados en los campos `director_academico_ids` o `personal_docente_ids`.
- **Visibilidad de Masters**: Los profesores de una asignatura pueden ver el Master padre en modo **solo lectura** para conocer el contexto del programa, pero no pueden editarlo.
- **Calificaciones**: Un profesor solo puede ver y editar las actas (`slide.channel.partner`) de los cursos que gestiona.
- **Evaluaciones**: El acceso a los archivos entregados por los alumnos y sus notas individuales está restringido a los responsables del contenido.

---

## 3. Matriz de Acceso (CSV)

| Modelo          | Grupo               | Leer | Crear | Editar | Borrar |
| :-------------- | :------------------ | :--: | :---: | :----: | :----: |
| `slide.channel` | Personal Docente    |  Sí  |  No   |   No   |   No   |
| `slide.channel` | Director Académico  |  Sí  |  Sí   |   Sí   |   No   |
| `slide.channel` | Administrador Univ. |  Sí  |  Sí   |   Sí   |   Sí   |

_Nota: El administrador de la universidad tiene un bypass total (`domain_force = [(1,'=',1)]`) para poder auditar cualquier curso en cualquier momento._
