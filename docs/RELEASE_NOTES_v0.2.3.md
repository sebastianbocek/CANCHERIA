# CANCHERIA v0.2.3

## Disponibilidad con hora exacta y fecha implícita

Esta versión corrige el caso conversacional:

```text
Cliente: Hola tenes cancha para las 4
Agente:  ¿Qué día te gustaría?
Cliente: Hoy
Agente:  [mostraba todos los horarios del día]
```

Cuando el transformer ya reconoce una hora exacta del turno actual y el cliente
no expresa otra fecha, la consulta se resuelve para **hoy**. Por ejemplo, a las
12:22, `para las 4` consulta directamente las `16:00`.

También se conserva el slot completo si una conversación iniciada con una
versión anterior ya quedó esperando el día: al responder `Hoy`, CANCHERIA
recupera la hora, el deporte y la duración pendientes.

## Fast path canónico

Las consultas reconocidas como `query_availability` quedan dentro del camino
canónico. Ya no se delegan al executor legacy por baja confianza, una excepción
interna o un resultado sin manejar; en esos casos se activa el cierre seguro y
la atención silenciosa del administrador.

## Verificación

- Reproducción artificial del incidente a las 12:22 con estado histórico del
  día anterior.
- Resultado verificado: `Jueves 08/10`, `16:00`, cuatro canchas disponibles.
- Prueba de continuidad `para las 4` → `Hoy` conservando `16:00`.
- Suite automatizada sobre la copia pública sanitizada.

```text
35331E2B0579EA30860DE3E6167C99F1CB8D72D2B1DE9D522D51CFB28A1C365C  InstaladorCancheria.exe
B1C7AFFEDA20D380C89D4A9103CAD6CC8262BEFA1194723BBADD59841881636D  InstaladorCancheriaLinux.run
A26FADC0F366F59DA93C8A5B683CDDBBC594F54D0D0B39EB094993E618184D28  CANCHERIA-update-windows.zip
0159724C875E6BFC02430A4B6E44C706C054A70E41D5795A503B5A49B585225F  CANCHERIA-update-linux.zip
ABFDCEDED5E455CCB6E845879B8252AC6C05161C84677FFF2A62C3FFBEC134CE  DEMO-CANCHERIA-CHAT.mp4
```
