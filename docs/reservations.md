# Reservations

The calendar engine now lives at `src/cancheria/domain/reservations/calendar.py`. It owns availability and booking mutations while preserving the original CSV/locking behavior. Runtime files are configured under `runtime/`.
