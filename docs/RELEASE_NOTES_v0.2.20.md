# CANCHERIA v0.2.20

Esta versión separa el encendido general de CANCHERIA del estado de sus respuestas automáticas.

## Cambios principales

- **Encendido tolerante a la API:** una clave de OpenAI vacía, inválida o no verificable ya no impide abrir WhatsApp ni ejecutar el servicio operativo y sus alertas.
- **APAGAR:** reemplaza al botón PAUSA anterior y detiene por completo el proceso, conservando la sesión local para el próximo inicio.
- **PAUSAR IA / REANUDAR IA:** permite suspender únicamente las respuestas automáticas sin cerrar WhatsApp. El texto del botón y el estado de la ventana reflejan inmediatamente el modo actual.
- **Sincronización con WhatsApp:** los comandos administrativos para pausar o reanudar el agente actualizan el mismo estado que utiliza la GUI.
- **Persistencia:** el estado se guarda en `runtime/ai_control.json`, carpeta que los instaladores y el actualizador ya preservan junto con los demás datos operativos.

## Comportamiento esperado

Si la API no está configurada, CANCHERIA muestra una advertencia en el panel de Actividad, pero permanece encendido. Después de corregir la clave desde Configuración, se recomienda apagar y encender una vez para que todo el proceso cargue la nueva configuración.
