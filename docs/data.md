# Automatismos y Datos (`data`)

El sistema utiliza procesos asíncronos (CRONs) para gestionar tareas que requieren ejecución periódica o que son costosas de procesar en tiempo real.

## 1. Motores de Publicación

### Publicación de Cursos (`slide.channel`)

- **ID**: `ir_cron_publicar_cursos_programados`
- **Frecuencia**: Cada 5 minutos.
- **Función**: Busca cursos en estado `programado` cuya `fecha_programada_publicacion` haya llegado y ejecuta el método `action_publicar()`. Esto asegura que los cursos se activen exactamente cuando se requiere sin intervención manual.

### Publicación de Contenidos (`slide.slide`)

- **ID**: `ir_cron_publicar_slides_programados`
- **Frecuencia**: Cada 5 minutos.
- **Función**: Publica slides individuales que tengan una `fecha_programada` alcanzada. Ideal para desbloquear temas progresivamente.

---

## 2. Motor de Certificación

### Emisión de Títulos (`slide.channel.partner`)

- **ID**: `ir_cron_emitir_titulos_pendientes`
- **Frecuencia**: Cada 5 minutos.
- **Función**: Procesa las inscripciones en estado `pendiente_certificar`.
  - Genera el título universitario.
  - Marca la inscripción como `certificado`.
  - Registra la fecha de emisión.
  - **Optimización**: Procesa en bloques de 50 registros para evitar sobrecarga del servidor en picos de graduación.

---

## 3. Configuración Técnica

- Todos los CRONs están definidos con `noupdate="1"`, lo que permite al administrador ajustar los intervalos de ejecución desde la interfaz de Odoo sin miedo a que se sobrescriban en futuras actualizaciones del módulo.
