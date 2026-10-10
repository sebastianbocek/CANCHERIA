# CANCHERIA v0.2.31

## Actualizador de Windows reparado

El auxiliar espera el cierre real de CANCHERIA, termina únicamente instancias residuales de `cancheria.exe` pertenecientes a la misma instalación y reintenta de forma acotada los reemplazos mientras Windows libera sus handles. Si aun así existe un bloqueo persistente, cancela antes de mezclar versiones y conserva la restauración automática.

## Caja contable real

- Ledger SQLite persistente, transaccional, append-only y con importes en centavos.
- Registro automático al confirmar señas, saldos, pagos totales e inscripciones de torneos.
- Idempotencia: repetir una confirmación no duplica dinero y confirmar el total después de una seña registra sólo el saldo.
- Ingresos y gastos manuales con fecha, método, cliente/proveedor, categoría, cancha, reserva relacionada y observaciones.
- Filtros Hoy, Ayer, Últimos 7 días, Mes actual, Mes anterior y rango personalizado.
- Cierres de caja con efectivo esperado/contado, diferencia, responsable y notas.
- Exportación CSV detallada compatible con Excel.

CANCHERIA no reconstruye cobros antiguos sin evidencia de cuándo se pagaron. El historial financiero confiable comienza con los movimientos registrados por esta versión; los saldos vigentes y el valor de reservas futuras se calculan desde los datos operativos actuales.
