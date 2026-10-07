##CALENDARIO

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import csv
import os
import datetime
from typing import List, Dict, Optional, Any, Tuple

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False
import re
import sys
import argparse
import threading
from contextlib import contextmanager
from typing import Optional, Tuple, List


def _configure_utf8_console_streams() -> None:
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


_configure_utf8_console_streams()


from cancheria.config.legacy_config import (
    ACTIVE_BOOKING_STATUSES,
    BOOKING_FIELDNAMES,
    BOOKINGS_CSV,
    CALL_SLOT_DURATION_MINUTES,
    COURTS,
    DEFAULT_COURT_NAME,
    DEFAULT_DEPOSIT_STATUS,
    DEFAULT_TURN_TYPE,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_PENDING,
    BOOKING_STATUS_RESERVED,
    FINISHED_BOOKINGS_CSV,
    MAX_BOOKING_SEARCH_DAYS,
    UPCOMING_BOOKINGS_LIMIT,
    descripcion_atencion_mensaje,
    obtener_franjas_atencion_minutos,
    obtener_hora_inicio_atencion,
    obtener_hora_por_defecto,
    validar_fecha_en_dias_atencion,
)

CALENDARIO_CSV = BOOKINGS_CSV
CALENDARIO_TERMINADAS_CSV = FINISHED_BOOKINGS_CSV
DURACION_MINUTOS = CALL_SLOT_DURATION_MINUTES
MAX_SLOTS_BUSQUEDA = MAX_BOOKING_SEARCH_DAYS
CANCHA_DEFAULT = DEFAULT_COURT_NAME

FIELDNAMES = BOOKING_FIELDNAMES


def _parse_hora(hora_str: str) -> Optional[datetime.time]:
    if not hora_str:
        return None
    m = re.match(r'^(\d{1,2}):(\d{2})$', hora_str.strip())
    if m:
        try:
            return datetime.time(int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _primera_hora_atencion_time() -> datetime.time:
    return _parse_hora(obtener_hora_inicio_atencion()) or datetime.time(9, 0)


def _parse_fecha_simple(
    fecha_str: str,
    anio_referencia: Optional[int] = None,
    asumir_proximo_anio_si_paso: bool = True
) -> Optional[datetime.date]:
    """
    Parsea fecha en formato DD/MM o DD/MM/YYYY
    Si no tiene anio, usa el anio de referencia o el anio actual
    """
    if not fecha_str:
        return None

    hoy = datetime.date.today()
    anio = anio_referencia if anio_referencia else hoy.year

    # Buscar patrón DD/MM/YYYY
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', fecha_str)
    if m:
        try:
            dia = int(m.group(1))
            mes = int(m.group(2))
            anio = int(m.group(3))
            return datetime.date(anio, mes, dia)
        except ValueError:
            pass

    # Buscar patrón DD/MM
    m = re.search(r'(\d{1,2})/(\d{1,2})', fecha_str)
    if m:
        try:
            dia = int(m.group(1))
            mes = int(m.group(2))
            fecha = datetime.date(anio, mes, dia)

            # Para proponer slots futuros, asumir próximo anio si ya pasó.
            # Para limpiar terminadas, comparar contra el anio actual.
            if asumir_proximo_anio_si_paso and fecha < hoy:
                fecha = datetime.date(anio + 1, mes, dia)

            return fecha
        except ValueError:
            pass

    return None


def _extraer_fecha_hora_de_row(
    row: dict,
    asumir_proximo_anio_si_paso: bool = True
) -> Tuple[Optional[datetime.date], Optional[datetime.time]]:
    """Extrae fecha y hora de una fila del calendario"""
    fecha_str = row.get("fecha", "")
    hora_str = row.get("hora", "")

    # El formato puede ser "Lunes 13/04", "13/04", o "13/04/2025"
    # Extraer solo la parte numérica de la fecha
    fecha_parseada = _parse_fecha_simple(
        fecha_str,
        asumir_proximo_anio_si_paso=asumir_proximo_anio_si_paso
    )

    hora = _parse_hora(hora_str)

    return fecha_parseada, hora


def _row_ya_paso(row: dict) -> bool:
    """Determina si una fila del calendario ya pasó respecto al datetime actual"""
    fecha, hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)

    if not fecha or not hora:
        return False

    ahora = datetime.datetime.now()

    # Crear datetime combinado
    fecha_hora_row = datetime.datetime.combine(fecha, hora)

    # Consideramos que ya pasó si la fecha/hora es anterior al momento actual
    return fecha_hora_row < ahora


def _texto_a_fecha(texto: str) -> Optional[datetime.date]:
    if not texto:
        return None
    hoy = datetime.date.today()
    t = texto.lower().strip()

    if t in ("hoy",):
        return hoy
    if t in ("mañana",):
        return hoy + datetime.timedelta(days=1)
    if t in ("pasado mañana", "pasado"):
        return hoy + datetime.timedelta(days=2)

    m_iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m_iso:
        try:
            return datetime.date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass

    dias_semana = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    }

    # Intentar extraer fecha numérica
    fecha_parseada = _parse_fecha_simple(texto, hoy.year)
    if fecha_parseada:
        return fecha_parseada

    for nombre, num in dias_semana.items():
        if nombre in t:
            dias_hasta = (num - hoy.weekday()) % 7
            if dias_hasta == 0:
                dias_hasta = 7
            return hoy + datetime.timedelta(days=dias_hasta)

    return None


def verificar_bloque_disponible(self, dia: str, hora_inicio: str, duracion_minutos: int, cancha: str = None) -> tuple:
    """Verifica si un bloque completo de tiempo está disponible."""
    hora_inicio_minutos = self._hora_a_minutos(hora_inicio)
    hora_fin_minutos = hora_inicio_minutos + duracion_minutos

    # Verificar cada slot de 60 minutos dentro del bloque
    hora_actual = hora_inicio_minutos
    while hora_actual < hora_fin_minutos:
        hora_str = self._minutos_a_hora(hora_actual)
        if not self.slot_esta_libre(dia, hora_str, cancha=cancha):
            return False, hora_str
        hora_actual += 60  # Avanzar de hora en hora

    return True, None

def reservar_bloque(self, dia: str, hora_inicio: str, duracion_minutos: int, 
                    telefono: str, nombre: str, website: str = "", 
                    cancha: str = None, estado: str = "reservado") -> tuple:
    """Reserva un bloque completo de tiempo."""
    hora_inicio_minutos = self._hora_a_minutos(hora_inicio)
    hora_fin_minutos = hora_inicio_minutos + duracion_minutos

    reservas_exitosas = []
    hora_actual = hora_inicio_minutos

    while hora_actual < hora_fin_minutos:
        hora_str = self._minutos_a_hora(hora_actual)
        ok, resultado = self.reservar(dia, hora_str, telefono, nombre, website, cancha=cancha, estado=estado)
        if not ok:
            # Rollback de reservas ya hechas
            for h in reservas_exitosas:
                self.cancelar(dia, h, telefono=telefono)
            return False, (dia, hora_str)
        reservas_exitosas.append(hora_str)
        hora_actual += 60

    return True, (dia, hora_inicio)

def actualizar_duracion_y_montos(self, telefono: str, duracion_horas: float, 
                                  precio_total: int, senia_valor: int, 
                                  monto_pendiente: int):
    """Actualiza el CSV con la duración y montos calculados."""
    reserva = self.obtener_reserva_por_telefono(telefono)
    if reserva:
        reserva["duracion_horas"] = duracion_horas
        reserva["precio_total"] = precio_total
        reserva["senia_valor"] = senia_valor
        reserva["monto_pendiente"] = monto_pendiente
        self._guardar_reserva_en_csv(reserva)  # Implementar según tu estructura


def _fecha_a_str(fecha: datetime.date) -> str:
    return fecha.strftime("%d/%m/%Y")


def _hora_a_str(hora: datetime.time) -> str:
    return hora.strftime("%H:%M")


def _sumar_minutos(hora: datetime.time, minutos: int) -> Optional[datetime.time]:
    total = hora.hour * 60 + hora.minute + minutos
    if not any(inicio <= total < fin for inicio, fin in obtener_franjas_atencion_minutos()):
        return None
    return datetime.time(total // 60, total % 60)


def _slots_del_dia(fecha: datetime.date) -> List[datetime.time]:
    if not validar_fecha_en_dias_atencion(fecha):
        return []
    slots = []
    for inicio, fin in obtener_franjas_atencion_minutos():
        total_min = inicio
        while total_min + DURACION_MINUTOS <= fin:
            slots.append(datetime.time(total_min // 60, total_min % 60))
            total_min += DURACION_MINUTOS
    return slots


def _slot_ya_paso(fecha: datetime.date, hora: datetime.time) -> bool:
    if not fecha or not hora:
        return False
    ahora = datetime.datetime.now()
    return datetime.datetime.combine(fecha, hora) <= ahora


class CalendarioLlamadas:

    def __init__(self, csv_path: str = CALENDARIO_CSV):
        self.csv_path = csv_path
        self.terminadas_path = CALENDARIO_TERMINADAS_CSV
        # V2.10: exclusión mutua intra-proceso + lock de archivo inter-proceso.
        # Todas las escrituras críticas usan el mismo namespace de lock.
        self._atomic_mutex = threading.RLock()
        self._atomic_local = threading.local()
        self._lock_path = f"{self.csv_path}.lock"
        self._init_csv()
        self._init_terminadas_csv()

    @contextmanager
    def atomic(self):
        """
        Sección crítica reentrante para CHECK + WRITE del calendario.

        - RLock evita carreras entre tasks/hilos del mismo proceso.
        - flock (Unix) / msvcrt.locking (Windows) evita carreras entre procesos.
        - Es reentrante: reservar bloques o batches pueden abrir una transacción
          externa y seguir llamando self.reservar() sin deadlock.
        """
        with self._atomic_mutex:
            depth = int(getattr(self._atomic_local, "depth", 0) or 0)
            if depth > 0:
                self._atomic_local.depth = depth + 1
                try:
                    yield
                finally:
                    self._atomic_local.depth -= 1
                return

            self._atomic_local.depth = 1
            lock_file = None
            try:
                lock_dir = os.path.dirname(os.path.abspath(self._lock_path))
                if lock_dir:
                    os.makedirs(lock_dir, exist_ok=True)
                lock_file = open(self._lock_path, "a+b")
                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)

                if _HAS_FCNTL:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                elif _HAS_MSVCRT:
                    # Windows: bloquear un byte conocido del sidecar. LK_LOCK espera.
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)

                yield
            finally:
                if lock_file is not None:
                    try:
                        if _HAS_FCNTL:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                        elif _HAS_MSVCRT:
                            lock_file.seek(0)
                            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    finally:
                        lock_file.close()
                self._atomic_local.depth = 0

    def _init_csv(self):
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
            print(f"[Calendario] Archivo creado: {self.csv_path}")
        else:
            self._migrar_columnas_si_hace_falta(self.csv_path)

    def _init_terminadas_csv(self):
        if not os.path.exists(self.terminadas_path):
            with open(self.terminadas_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
            print(f"[Calendario] Archivo de terminadas creado: {self.terminadas_path}")
        else:
            self._migrar_columnas_si_hace_falta(self.terminadas_path)

    def _normalizar_row(self, row: dict) -> dict:
        normalizada = {field: row.get(field, "") for field in FIELDNAMES}
        normalizada["cancha"] = normalizada.get("cancha") or CANCHA_DEFAULT
        normalizada["tipo_turno"] = normalizada.get("tipo_turno") or DEFAULT_TURN_TYPE
        normalizada["duracion_minutos"] = normalizada.get("duracion_minutos") or str(DURACION_MINUTOS)
        normalizada["senia_estado"] = normalizada.get("senia_estado") or DEFAULT_DEPOSIT_STATUS
        return normalizada

    @staticmethod
    def _reservation_id_number(value: Any) -> Optional[int]:
        match = re.fullmatch(r"(?:ID[-_ ]*)?(\d+)", str(value or "").strip(), re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _reservation_id_sequence_path(self) -> str:
        return f"{self.csv_path}.reservation_id.seq"

    def _reservation_id_high_watermark_unlocked(
        self,
        rows: Optional[List[dict]] = None,
    ) -> int:
        all_rows = list(rows or []) + self._leer_terminadas()
        used = [
            number
            for number in (
                self._reservation_id_number(row.get("reservation_id"))
                for row in all_rows
            )
            if number is not None
        ]
        sequence_value = 0
        try:
            with open(self._reservation_id_sequence_path(), "r", encoding="utf-8") as handle:
                sequence_value = int(str(handle.read() or "0").strip() or 0)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            sequence_value = 0
        return max([sequence_value, *used], default=0)

    def _persist_reservation_id_high_watermark_unlocked(self, value: int) -> None:
        value = max(int(value or 0), self._reservation_id_high_watermark_unlocked([]))
        if value <= 0:
            return
        path = self._reservation_id_sequence_path()
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        temp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                handle.write(str(value))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def _next_reservation_id_unlocked(self, rows: Optional[List[dict]] = None) -> str:
        next_id = self._reservation_id_high_watermark_unlocked(rows) + 1
        self._persist_reservation_id_high_watermark_unlocked(next_id)
        return str(next_id)

    def _ensure_reservation_ids(self, rows: List[dict]) -> bool:
        """Asigna un ID persistente por reserva lógica, no por fila horaria."""
        changed = False
        def is_booking(row: dict) -> bool:
            estado = str(row.get("estado") or "").strip().lower()
            senia_estado = str(row.get("senia_estado") or "").strip().lower()
            has_owner = bool(
                str(row.get("telefono") or "").strip()
                or str(row.get("nombre") or "").strip()
            )
            return has_owner and (
                estado in {
                    *(str(status or "").strip().lower() for status in ACTIVE_BOOKING_STATUSES),
                    str(BOOKING_STATUS_CANCELLED).strip().lower(),
                    "hold_expirado",
                    "no_show",
                }
                or senia_estado in {"pendiente", "pendiente_efectivo", "pagada"}
            )

        def owner_key(row: dict) -> tuple:
            phone = re.sub(r"\D", "", str(row.get("telefono") or ""))
            name = str(row.get("nombre") or "").strip().casefold()
            return (
                phone or name,
                str(row.get("fecha") or "").strip(),
                str(row.get("cancha") or "").strip().casefold(),
            )

        def slot_minute(row: dict) -> Optional[int]:
            parsed = _parse_hora(str(row.get("hora") or ""))
            return parsed.hour * 60 + parsed.minute if parsed else None

        def logical_slot_count(row: dict) -> int:
            try:
                hours = float(str(row.get("duracion_horas") or "").replace(",", "."))
                minutes = int(round(hours * 60))
            except (TypeError, ValueError):
                try:
                    minutes = int(float(row.get("duracion_minutos") or DURACION_MINUTOS))
                except (TypeError, ValueError):
                    minutes = DURACION_MINUTOS
            return max(1, (minutes + DURACION_MINUTOS - 1) // DURACION_MINUTOS)

        missing = [
            index for index, row in enumerate(rows)
            if is_booking(row) and not str(row.get("reservation_id") or "").strip()
        ]
        missing.sort(key=lambda index: (
            owner_key(rows[index]),
            slot_minute(rows[index]) if slot_minute(rows[index]) is not None else 10**9,
        ))
        if not missing:
            high_watermark = self._reservation_id_high_watermark_unlocked(rows)
            if high_watermark > 0:
                self._persist_reservation_id_high_watermark_unlocked(high_watermark)
            return changed

        next_id = int(self._next_reservation_id_unlocked(rows))
        assigned = set()

        for index in missing:
            if index in assigned:
                continue
            row = rows[index]
            current_minute = slot_minute(row)
            reservation_id = str(next_id)
            next_id += 1
            target_minutes = {
                current_minute + offset * DURACION_MINUTOS
                for offset in range(logical_slot_count(row))
            } if current_minute is not None else {None}

            for candidate_index in missing:
                if candidate_index in assigned:
                    continue
                candidate = rows[candidate_index]
                if owner_key(candidate) != owner_key(row):
                    continue
                if slot_minute(candidate) not in target_minutes:
                    continue
                if logical_slot_count(candidate) != logical_slot_count(row):
                    continue
                candidate["reservation_id"] = reservation_id
                assigned.add(candidate_index)
                changed = True
        if changed:
            self._persist_reservation_id_high_watermark_unlocked(next_id - 1)
        return changed

    def asegurar_ids_reservas(self) -> List[dict]:
        """Migra IDs faltantes de todas las reservas bajo lock."""
        with self.atomic():
            rows = self._leer_todos()
            if self._ensure_reservation_ids(rows):
                self._escribir_todos(rows, ordenar=True)
            return rows

    def asegurar_ids_reservas_pendientes(self) -> List[dict]:
        """Alias compatible: los IDs ahora cubren pendientes y confirmadas."""
        return self.asegurar_ids_reservas()

    def siguiente_reservation_id(self) -> str:
        """Reserva el próximo número lógico; debe llamarse dentro del write atómico."""
        with self.atomic():
            rows = self._leer_todos()
            return self._next_reservation_id_unlocked(rows)

    def _migrar_columnas_si_hace_falta(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = [self._normalizar_row(dict(row)) for row in reader]
                fieldnames = reader.fieldnames or []

            self._ensure_reservation_ids(rows)

            if fieldnames != FIELDNAMES:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"[Calendario] Columnas migradas para turnos: {path}")
        except Exception as e:
            print(f"[Calendario] Error migrando columnas de {path}: {e}")

    def _leer_todos(self) -> List[dict]:
        rows = []
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(self._normalizar_row(dict(row)))
        except Exception as e:
            print(f"[Calendario] Error leyendo: {e}")
        return rows

    def _leer_terminadas(self) -> List[dict]:
        rows = []
        try:
            if os.path.exists(self.terminadas_path):
                with open(self.terminadas_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(self._normalizar_row(dict(row)))
        except Exception as e:
            print(f"[Calendario] Error leyendo terminadas: {e}")
        return rows

    def _ordenar_filas(self, rows: List[dict]) -> List[dict]:
        """Ordena las filas por fecha y hora (las más próximas primero)"""
        def clave_ordenamiento(row):
            fecha, hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)

            if not fecha:
                fecha = datetime.date.max
            if not hora:
                hora = datetime.time.max

            return (fecha, hora)

        # Ordenar todas las filas (reservadas y pendientes)
        rows.sort(key=clave_ordenamiento)
        return rows

    def _mover_terminadas(self) -> int:
        """Mueve las filas ya pasadas al archivo de terminadas y las elimina del principal"""
        rows = self._leer_todos()

        if not rows:
            print("[Calendario] No hay filas para procesar")
            return 0

        ahora = datetime.datetime.now()
        print(f"[Calendario] Procesando {len(rows)} filas. Hora actual: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")

        # Separar filas que ya pasaron de las que no
        filas_activas = []
        filas_terminadas = []

        for row in rows:
            fecha, hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)

            if fecha and hora:
                fecha_hora_row = datetime.datetime.combine(fecha, hora)

                # Si la fecha/hora es anterior al momento actual
                if fecha_hora_row < ahora:
                    print(f"   [MOVER] {row.get('fecha')} {row.get('hora')} - {row.get('nombre', '?')} (ya pasó)")
                    filas_terminadas.append(row)
                else:
                    print(f"   [MANTENER] {row.get('fecha')} {row.get('hora')} - {row.get('nombre', '?')} (futuro)")
                    filas_activas.append(row)
            else:
                print(f"   [WARN] No se pudo parsear fecha/hora: {row.get('fecha')} {row.get('hora')}")
                filas_activas.append(row)

        if filas_terminadas:
            # Leer filas existentes en terminadas
            terminadas_existentes = self._leer_terminadas()

            # Agregar las nuevas terminadas (evitar duplicados)
            ids_existentes = {f"{r.get('fecha')}_{r.get('hora')}_{r.get('telefono')}" for r in terminadas_existentes}

            for row in filas_terminadas:
                row_id = f"{row.get('fecha')}_{row.get('hora')}_{row.get('telefono')}"
                if row_id not in ids_existentes:
                    terminadas_existentes.append(row)
                    ids_existentes.add(row_id)

            # Escribir todas las terminadas
            try:
                with open(self.terminadas_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(terminadas_existentes)

                print(f"[Calendario] {len(filas_terminadas)} llamadas movidas a {self.terminadas_path}")
            except Exception as e:
                print(f"[Calendario] Error moviendo terminadas: {e}")
                return 0

            # Actualizar el archivo principal con solo las filas activas
            self._escribir_todos(filas_activas, ordenar=True)
            return len(filas_terminadas)
        else:
            print("[Calendario] No hay llamadas terminadas para mover")
            # Aún así, ordenar el archivo
            self._escribir_todos(rows, ordenar=True)

        return 0

    def _cancha_row(self, row: dict) -> str:
        return row.get("cancha") or CANCHA_DEFAULT

    def _esta_reservado(self, fecha: datetime.date, hora: datetime.time, cancha: str = CANCHA_DEFAULT) -> bool:
        fecha_str = _fecha_a_str(fecha)
        hora_str = _hora_a_str(hora)
        cancha = cancha or CANCHA_DEFAULT
        for row in self._leer_todos():
            row_fecha, _ = _extraer_fecha_hora_de_row(row)
            if (row_fecha and _fecha_a_str(row_fecha) == fecha_str and
                    row.get("hora") == hora_str and
                    self._cancha_row(row) == cancha):
                estado = row.get("estado", "")
                if str(estado).lower() in ACTIVE_BOOKING_STATUSES:
                    return True
        return False

    def canchas_disponibles(self, dia_texto: str, hora_texto: str) -> List[str]:
        fecha = _texto_a_fecha(dia_texto)
        hora = _parse_hora(hora_texto)
        if not fecha or not hora:
            print(
                f"[Calendario] Entrada invalida para disponibilidad: "
                f"dia={dia_texto!r}, hora={hora_texto!r}"
            )
            return []
        if not validar_fecha_en_dias_atencion(fecha):
            print(f"[Calendario] Dia fuera de atencion: {dia_texto} ({descripcion_atencion_mensaje()})")
            return []
        if _slot_ya_paso(fecha, hora):
            print(f"[Calendario] Slot pasado/no disponible: {dia_texto} {hora_texto}")
            return []
        disponibles = []
        for court in COURTS or [{"name": CANCHA_DEFAULT}]:
            cancha = court["name"]
            if not self._esta_reservado(fecha, hora, cancha):
                disponibles.append(cancha)
        return disponibles

    def bloquear_dia_completo(self, dia_texto: str, motivo: str = "Cerrado por admin", cancha: str = None) -> Dict[str, Any]:
        fecha = _texto_a_fecha(dia_texto)
        if not fecha:
            return {"ok": False, "motivo": "fecha_invalida", "bloqueados": 0, "ocupados": 0, "total": 0}

        rows = self._leer_todos()
        fecha_str = _fecha_a_str(fecha)
        nombre_dia = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"][fecha.weekday()]
        dia_str = f"{nombre_dia} {fecha.strftime('%d/%m')}"
        courts = COURTS or [{"name": CANCHA_DEFAULT}]
        if cancha:
            courts = [court for court in courts if court.get("name") == cancha]
            if not courts:
                return {"ok": False, "motivo": "cancha_invalida", "bloqueados": 0, "ocupados": 0, "total": 0}
        slots = _slots_del_dia(fecha)
        bloqueados = 0
        ocupados = 0
        ya_bloqueados = 0

        for slot in slots:
            hora_str = _hora_a_str(slot)
            for court in courts:
                cancha = court["name"]
                fila_activa = None
                for row in rows:
                    row_fecha, _ = _extraer_fecha_hora_de_row(row)
                    if (
                        row_fecha
                        and _fecha_a_str(row_fecha) == fecha_str
                        and row.get("hora") == hora_str
                        and self._cancha_row(row) == cancha
                        and str(row.get("estado", "")).lower() in ACTIVE_BOOKING_STATUSES
                    ):
                        fila_activa = row
                        break

                if fila_activa:
                    if str(fila_activa.get("telefono") or "").startswith("ADMIN:CERRADO"):
                        ya_bloqueados += 1
                    else:
                        ocupados += 1
                    continue

                rows.append({
                    "fecha": dia_str,
                    "hora": hora_str,
                    "estado": BOOKING_STATUS_RESERVED,
                    "telefono": f"ADMIN:CERRADO:{fecha.isoformat()}",
                    "nombre": "CERRADO",
                    "cancha": cancha,
                    "tipo_turno": DEFAULT_TURN_TYPE,
                    "duracion_minutos": str(DURACION_MINUTOS),
                    "duracion_horas": "",
                    "precio": "",
                    "precio_total": "",
                    "senia_estado": "no_requiere",
                    "senia_monto": "",
                    "monto_pendiente": "",
                    "notas": motivo,
                    "reservado_en": datetime.datetime.now().isoformat(timespec="seconds"),
                })
                bloqueados += 1

        if bloqueados:
            self._escribir_todos(rows, ordenar=True)

        return {
            "ok": True,
            "dia": dia_str,
            "fecha": fecha.isoformat(),
            "bloqueados": bloqueados,
            "ocupados": ocupados,
            "ya_bloqueados": ya_bloqueados,
            "total": len(slots) * len(courts),
            "cancha": cancha or "",
        }

    def desbloquear_dia_completo(self, dia_texto: str, cancha: str = None) -> Dict[str, Any]:
        fecha = _texto_a_fecha(dia_texto)
        if not fecha:
            return {"ok": False, "motivo": "fecha_invalida", "desbloqueados": 0, "conservados": 0}

        if cancha:
            canchas_validas = {court.get("name") for court in (COURTS or [{"name": CANCHA_DEFAULT}])}
            if cancha not in canchas_validas:
                return {"ok": False, "motivo": "cancha_invalida", "desbloqueados": 0, "conservados": 0}

        fecha_str = _fecha_a_str(fecha)
        rows = self._leer_todos()
        rows_nuevas = []
        desbloqueados = 0
        conservados = 0

        for row in rows:
            row_fecha, _ = _extraer_fecha_hora_de_row(row)
            es_fecha_objetivo = row_fecha and _fecha_a_str(row_fecha) == fecha_str
            es_bloqueo_admin = (
                str(row.get("telefono") or "").startswith("ADMIN:CERRADO")
                or str(row.get("nombre") or "").strip().upper() == "CERRADO"
            )
            es_cancha_objetivo = not cancha or self._cancha_row(row) == cancha
            if es_fecha_objetivo and es_cancha_objetivo and es_bloqueo_admin:
                desbloqueados += 1
                continue
            if es_fecha_objetivo:
                conservados += 1
            rows_nuevas.append(row)

        if desbloqueados:
            self._escribir_todos(rows_nuevas, ordenar=True)

        nombre_dia = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"][fecha.weekday()]
        return {
            "ok": True,
            "dia": f"{nombre_dia} {fecha.strftime('%d/%m')}",
            "fecha": fecha.isoformat(),
            "desbloqueados": desbloqueados,
            "conservados": conservados,
            "cancha": cancha or "",
        }

    def _escribir_todos(self, rows: List[dict], ordenar: bool = True):
        """
        Escribe el CSV por reemplazo atómico.

        El lock de negocio lo provee atomic(); os.replace evita dejar un CSV
        parcialmente escrito si el proceso se corta durante el flush.
        """
        self._ensure_reservation_ids(rows)
        if ordenar:
            rows = self._ordenar_filas(rows)

        directory = os.path.dirname(os.path.abspath(self.csv_path)) or "."
        os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.csv_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(tmp_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, self.csv_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def ordenar_y_limpiar_archivo(self):
        """Ordena el archivo CSV por fecha y hora y mueve las llamadas pasadas a terminadas"""
        print("=" * 60)
        print("[Calendario] Iniciando limpieza y ordenamiento...")
        print("=" * 60)

        # Mostrar contenido actual
        rows = self._leer_todos()
        print(f"[Calendario] Filas actuales en {self.csv_path}: {len(rows)}")
        for row in rows:
            print(f"   - {row.get('fecha')} {row.get('hora')} | {row.get('nombre')} | estado: {row.get('estado')}")

        # Mover las llamadas terminadas
        movidas = self._mover_terminadas()

        # Mostrar resultado final
        rows_final = self._leer_todos()
        print(f"\n[Calendario] Filas restantes en {self.csv_path}: {len(rows_final)}")
        for row in rows_final:
            print(f"   - {row.get('fecha')} {row.get('hora')} | {row.get('nombre')}")

        if movidas > 0:
            print(f"\n[Calendario] ✅ Proceso completado. {movidas} llamadas movidas a terminadas.")
        else:
            print("\n[Calendario] ✅ Proceso completado. Sin llamadas terminadas para mover.")

        print("=" * 60)

    def slot_esta_libre(self, dia_texto: str, hora_texto: str, cancha: str = None) -> bool:
        fecha = _texto_a_fecha(dia_texto)
        hora = _parse_hora(hora_texto)
        if not fecha or not hora:
            print(
                f"   [Calendario] Entrada invalida para verificar slot: "
                f"dia={dia_texto!r}, hora={hora_texto!r}"
            )
            return False
        if not validar_fecha_en_dias_atencion(fecha):
            print(f"   [Calendario] Dia fuera de atencion: {dia_texto} ({descripcion_atencion_mensaje()})")
            return False
        if _slot_ya_paso(fecha, hora):
            print(f"   📅 [Calendario] Slot pasado/no disponible: {dia_texto} {hora_texto}")
            return False
        if cancha:
            return not self._esta_reservado(fecha, hora, cancha)
        return bool(self.canchas_disponibles(dia_texto, hora_texto))

    # ============================================================
    # 🆕 NUEVA FUNCIÓN: Verificar disponibilidad por cancha específica
    # ============================================================
    def slot_esta_libre_en_cancha(self, dia: str, hora: str, cancha: str) -> bool:
        """
        Verifica si un horario específico está libre en una cancha específica.

        Args:
            dia: Fecha en formato "Lunes 26/05" o "hoy", "mañana"
            hora: Hora en formato "HH:MM"
            cancha: Nombre de la cancha (ej: "Cancha 1")

        Returns:
            True si el horario está libre en esa cancha, False si está ocupado
        """
        try:
            fecha = _texto_a_fecha(dia)
            hora_obj = _parse_hora(hora)

            if not fecha or not hora_obj:
                print(f"   ⚠️ [Calendario] No se pudo parsear fecha/hora: dia={dia}, hora={hora}")
                return False

            if not validar_fecha_en_dias_atencion(fecha):
                print(f"   [Calendario] {cancha} no disponible: {dia}; atendemos {descripcion_atencion_mensaje()}")
                return False

            if _slot_ya_paso(fecha, hora_obj):
                print(f"   📅 [Calendario] {cancha} no disponible: {dia} a las {hora} ya pasó")
                return False

            # Verificar si está reservado
            esta_ocupado = self._esta_reservado(fecha, hora_obj, cancha)

            if esta_ocupado:
                print(f"   📅 [Calendario] {cancha} ocupada el {dia} a las {hora}")
                return False
            else:
                print(f"   📅 [Calendario] {cancha} libre el {dia} a las {hora}")
                return True

        except Exception as e:
            print(f"⚠️ [Calendario] Error en slot_esta_libre_en_cancha: {e}")
            import traceback
            traceback.print_exc()
            return False

    def proximo_slot_libre_desde(
        self,
        fecha_inicio: datetime.date,
        hora_inicio: datetime.time,
        cancha: str = None
    ) -> Tuple[str, str]:
        NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        hoy = datetime.date.today()
        aplicar_hora_inicio = True

        for dias_offset in range(MAX_SLOTS_BUSQUEDA):
            fecha_candidata = fecha_inicio + datetime.timedelta(days=dias_offset)
            slots = _slots_del_dia(fecha_candidata)
            if not slots:
                continue

            for slot in slots:
                if aplicar_hora_inicio and slot < hora_inicio:
                    continue
                if fecha_candidata == hoy:
                    ahora = datetime.datetime.now().time()
                    if slot <= ahora:
                        continue
                slot_libre = (
                    not self._esta_reservado(fecha_candidata, slot, cancha)
                    if cancha
                    else any(
                        not self._esta_reservado(fecha_candidata, slot, court["name"])
                        for court in (COURTS or [{"name": CANCHA_DEFAULT}])
                    )
                )
                if slot_libre:
                    nombre_dia = NOMBRES_DIAS[fecha_candidata.weekday()]
                    dia_str = f"{nombre_dia} {fecha_candidata.strftime('%d/%m')}"
                    hora_str = _hora_a_str(slot)
                    return dia_str, hora_str
            aplicar_hora_inicio = False

        fallback = hoy + datetime.timedelta(days=1)
        for dias_offset in range(1, 8):
            candidata = hoy + datetime.timedelta(days=dias_offset)
            if validar_fecha_en_dias_atencion(candidata):
                fallback = candidata
                break
        nombre_dia = NOMBRES_DIAS[fallback.weekday()]
        return f"{nombre_dia} {fallback.strftime('%d/%m')}", obtener_hora_por_defecto("mañana")

    def proximo_slot_cercano(
        self,
        dia_preferido: Optional[str] = None,
        hora_preferida: Optional[str] = None,
        cancha: Optional[str] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Busca un slot libre priorizando la intención del usuario.
        A diferencia de proximo_slot_libre_desde, no cae al primer horario de apertura
        apenas cambia de día: intenta conservar una hora cercana a la pedida.
        """
        NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        hoy = datetime.date.today()
        ahora = datetime.datetime.now().time()

        fecha_inicio = _texto_a_fecha(dia_preferido) if dia_preferido else hoy
        if not fecha_inicio or fecha_inicio < hoy:
            fecha_inicio = hoy

        hora_objetivo = _parse_hora(hora_preferida) if hora_preferida else _primera_hora_atencion_time()
        if not hora_objetivo:
            hora_objetivo = _primera_hora_atencion_time()
        objetivo_min = hora_objetivo.hour * 60 + hora_objetivo.minute

        candidatos = []
        for dias_offset in range(MAX_SLOTS_BUSQUEDA):
            fecha_candidata = fecha_inicio + datetime.timedelta(days=dias_offset)
            slots = _slots_del_dia(fecha_candidata)
            if not slots:
                continue

            for slot in slots:
                if fecha_candidata == hoy and slot <= ahora:
                    continue

                slot_libre = (
                    not self._esta_reservado(fecha_candidata, slot, cancha)
                    if cancha
                    else any(
                        not self._esta_reservado(fecha_candidata, slot, court["name"])
                        for court in (COURTS or [{"name": CANCHA_DEFAULT}])
                    )
                )
                if not slot_libre:
                    continue

                slot_min = slot.hour * 60 + slot.minute
                diferencia_min = abs(slot_min - objetivo_min)
                score = diferencia_min + (dias_offset * 180)
                candidatos.append((score, dias_offset, diferencia_min, slot_min, fecha_candidata, slot))

        if not candidatos:
            return None

        _, _, _, _, fecha_elegida, slot_elegido = min(candidatos, key=lambda item: item[:4])
        nombre_dia = NOMBRES_DIAS[fecha_elegida.weekday()]
        return f"{nombre_dia} {fecha_elegida.strftime('%d/%m')}", _hora_a_str(slot_elegido)

    def proximo_slot_libre(
        self,
        dia_preferido: Optional[str] = None,
        hora_preferida: Optional[str] = None,
        cancha: Optional[str] = None
    ) -> Tuple[str, str]:
        hoy = datetime.date.today()

        cercano = self.proximo_slot_cercano(
            dia_preferido=dia_preferido,
            hora_preferida=hora_preferida,
            cancha=cancha
        )
        if cercano:
            return cercano

        fecha_inicio = _texto_a_fecha(dia_preferido) if dia_preferido else hoy + datetime.timedelta(days=1)
        if not fecha_inicio or fecha_inicio < hoy:
            fecha_inicio = hoy + datetime.timedelta(days=1)

        hora_inicio = _parse_hora(hora_preferida) if hora_preferida else _primera_hora_atencion_time()
        if not hora_inicio:
            hora_inicio = _primera_hora_atencion_time()

        return self.proximo_slot_libre_desde(fecha_inicio, hora_inicio, cancha=cancha)

    def reservar(
        self,
        dia_texto: str,
        hora_texto: str,
        telefono: str,
        nombre: str = "",
        website: str = "",
        cancha: str = None,
        estado: str = BOOKING_STATUS_RESERVED,
        senia_estado: str = "",
        senia_monto: str = "",
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Tuple[str, str]]:
        """CHECK + WRITE atómico para un slot."""
        with self.atomic():
            return self._reservar_unlocked(
                dia_texto, hora_texto, telefono, nombre, website,
                cancha=cancha, estado=estado, senia_estado=senia_estado,
                senia_monto=senia_monto, extra_fields=extra_fields,
            )

    def _reservar_unlocked(
        self,
        dia_texto: str,
        hora_texto: str,
        telefono: str,
        nombre: str = "",
        website: str = "",
        cancha: str = None,
        estado: str = BOOKING_STATUS_RESERVED,
        senia_estado: str = "",
        senia_monto: str = "",
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Tuple[str, str]]:
        """
        Reserva un turno en el calendario.
        Cada combinación única (teléfono/nombre + fecha + hora + cancha) se guarda en su propia fila.
        No sobreescribe turnos de otros días/horas del mismo contacto.
        """
        fecha = _texto_a_fecha(dia_texto)
        hora = _parse_hora(hora_texto)
        cancha_solicitada = cancha is not None
        cancha = cancha or CANCHA_DEFAULT

        # ============================================================
        # 🔧 Verificar si el usuario YA TIENE una reserva con seña pagada
        # para ESTE mismo slot (fecha+hora+cancha)
        # Si es un slot DIFERENTE, NO heredar la seña de otro turno
        # ============================================================
        if not fecha or not hora:
            print(
                f"[Calendario] Reserva rechazada por fecha/hora invalida: "
                f"dia={dia_texto!r}, hora={hora_texto!r}"
            )
            return False, ("", "")

        if not validar_fecha_en_dias_atencion(fecha):
            print(f"[Calendario] Intento de reserva fuera de dias de atencion: {dia_texto} {hora_texto}")
            alt_dia, alt_hora = self.proximo_slot_libre_desde(fecha, hora, cancha=cancha)
            return False, (alt_dia, alt_hora)

        if _slot_ya_paso(fecha, hora):
            print(f"[Calendario] Intento de reserva en horario pasado: {dia_texto} {hora_texto}")
            alt_dia, alt_hora = self.proximo_slot_libre_desde(fecha, datetime.datetime.now().time(), cancha=cancha)
            return False, (alt_dia, alt_hora)

        canchas_disponibles = self.canchas_disponibles(dia_texto, hora_texto)
        if not cancha_solicitada and cancha not in canchas_disponibles and canchas_disponibles:
            cancha = canchas_disponibles[0]

        NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        nombre_dia = NOMBRES_DIAS[fecha.weekday()]
        dia_str = f"{nombre_dia} {fecha.strftime('%d/%m')}"
        hora_str = _hora_a_str(hora)

        # ============================================================
        # 🔧 Verificar si YA EXISTE una fila para este slot exacto
        # (misma fecha + hora + cancha), independientemente del contacto
        # ============================================================
        fecha_str = _fecha_a_str(fecha)
        slot_existente_idx = None
        slot_existente_del_mismo_contacto = False

        for i, row in enumerate(self._leer_todos()):
            row_fecha, _ = _extraer_fecha_hora_de_row(row)
            if not row_fecha:
                continue
            if (
                _fecha_a_str(row_fecha) == fecha_str
                and row.get("hora") == hora_str
                and self._cancha_row(row) == cancha
            ):
                estado_row = str(row.get("estado", "")).lower()
                es_activo = estado_row in ACTIVE_BOOKING_STATUSES

                # ¿Es del mismo contacto?
                mismo_telefono = telefono and row.get("telefono") == telefono
                mismo_nombre = nombre and row.get("nombre", "").lower() == nombre.lower()

                if mismo_telefono or mismo_nombre:
                    slot_existente_idx = i
                    slot_existente_del_mismo_contacto = True
                    # Preservar seña pagada si ya estaba en este slot
                    if row.get("senia_estado") == "pagada" and senia_estado != "pagada":
                        senia_estado = "pagada"
                        senia_monto = row.get("senia_monto", senia_monto)
                        estado = BOOKING_STATUS_RESERVED
                        print(f"   🔧 [CALENDARIO] Preservando seña pagada desde reserva existente: {senia_monto}")
                    break
                elif es_activo:
                    # Slot ocupado por OTRO contacto
                    print(f"[Calendario] Slot ocupado por otro: {dia_texto} {hora_texto}")
                    siguiente_hora = _sumar_minutos(hora, DURACION_MINUTOS)
                    if siguiente_hora:
                        alt_dia, alt_hora = self.proximo_slot_libre_desde(fecha, siguiente_hora, cancha=cancha)
                    else:
                        fecha_siguiente = fecha + datetime.timedelta(days=1)
                        alt_dia, alt_hora = self.proximo_slot_libre_desde(
                            fecha_siguiente,
                            _primera_hora_atencion_time(),
                            cancha=cancha
                        )
                    print(f"[Calendario] Alternativa encontrada: {alt_dia} {alt_hora}")
                    return False, (alt_dia, alt_hora)

        # ============================================================
        # 🔧 Escribir en CSV:
        # - Si ya existe fila del mismo contacto en este slot → actualizar esa fila
        # - Si no existe → agregar fila nueva (sin tocar otros turnos del contacto)
        # ============================================================
        if slot_existente_del_mismo_contacto and slot_existente_idx is not None:
            # Actualizar la fila existente para este slot
            self._upsert_fila_slot(
                dia_str, hora_str, telefono, nombre, website,
                fecha_obj=fecha, hora_obj=hora,
                cancha=cancha, estado=estado,
                senia_estado=senia_estado, senia_monto=senia_monto,
                extra_fields=extra_fields
            )
            print(f"[Calendario] Actualizado slot existente: {dia_str} {hora_str} {cancha} para {nombre or telefono} (seña: {senia_estado})")
        else:
            # Insertar fila nueva — no tocar otras filas del mismo contacto
            self._insertar_fila_nueva(
                dia_str, hora_str, telefono, nombre, website,
                fecha_obj=fecha, hora_obj=hora,
                cancha=cancha, estado=estado,
                senia_estado=senia_estado, senia_monto=senia_monto,
                extra_fields=extra_fields
            )
            print(f"[Calendario] Reservado nuevo slot: {dia_str} {hora_str} {cancha} para {nombre or telefono} (seña: {senia_estado})")

        return True, (dia_str, hora_str)

    def reprogramar_reserva(
        self,
        telefono: str,
        nombre: str,
        dia_texto: str,
        hora_texto: str,
        senia_estado_preservado: str = "",
        senia_monto_preservado: str = "",
        reserva_objetivo: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Tuple[str, str, str]]:
        """Reprogramación atómica; reserva_objetivo desambigua contactos con varios turnos."""
        with self.atomic():
            return self._reprogramar_reserva_unlocked(
                telefono, nombre, dia_texto, hora_texto,
                senia_estado_preservado=senia_estado_preservado,
                senia_monto_preservado=senia_monto_preservado,
                reserva_objetivo=reserva_objetivo,
            )

    def _reprogramar_reserva_unlocked(
        self,
        telefono: str,
        nombre: str,
        dia_texto: str,
        hora_texto: str,
        senia_estado_preservado: str = "",
        senia_monto_preservado: str = "",
        reserva_objetivo: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Tuple[str, str, str]]:
        """
        Reprograma una reserva existente modificando solo fecha y hora.

        CRÍTICO: Preserva TODO el estado original:
        - Si la reserva tenía estado 'reservado' (seña pagada) → se mantiene 'reservado'
        - Si tenía seña 'pagada' → se mantiene 'pagada'
        - NUNCA se degrada a 'pendiente' a menos que originalmente lo fuera

        CORREGIDO: SOLO elimina duplicados que sean EXACTAMENTE el mismo día, hora y cancha
        que la reserva que estamos reprogramando. NO elimina otros turnos válidos del mismo contacto.
        """
        fecha = _texto_a_fecha(dia_texto)
        hora = _parse_hora(hora_texto)
        if not fecha or not hora:
            print(f"[Calendario] No se pudo reprogramar: fecha/hora inválida ({dia_texto} {hora_texto})")
            return False, (dia_texto, hora_texto, "")

        if not validar_fecha_en_dias_atencion(fecha):
            print(f"[Calendario] Intento de reprogramación fuera de dias de atencion: {dia_texto} {hora_texto}")
            alt_dia, alt_hora = self.proximo_slot_libre_desde(fecha, hora)
            return False, (alt_dia, alt_hora, "")

        if _slot_ya_paso(fecha, hora):
            print(f"[Calendario] Intento de reprogramación a horario pasado: {dia_texto} {hora_texto}")
            alt_dia, alt_hora = self.proximo_slot_libre_desde(fecha, datetime.datetime.now().time())
            return False, (alt_dia, alt_hora, "")

        rows = self._leer_todos()
        telefono_buscar = str(telefono or "").strip()
        nombre_buscar = str(nombre or "").strip().lower()
        if telefono_buscar.startswith("NOMBRE:") and not nombre_buscar:
            nombre_buscar = telefono_buscar.replace("NOMBRE:", "").strip().lower()

        idx_reserva = None
        for idx, row in enumerate(rows):
            estado_row = str(row.get("estado", "")).lower()
            if estado_row not in ACTIVE_BOOKING_STATUSES:
                continue
            row_telefono = str(row.get("telefono", "")).strip()
            row_nombre = str(row.get("nombre", "")).strip().lower()
            coincide_telefono = bool(telefono_buscar and row_telefono == telefono_buscar)
            coincide_nombre = bool(nombre_buscar and row_nombre == nombre_buscar)
            if not (coincide_telefono or coincide_nombre):
                continue

            if reserva_objetivo:
                objetivo_fecha = _texto_a_fecha(str(reserva_objetivo.get("fecha") or reserva_objetivo.get("dia") or ""))
                row_fecha_obj, _ = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)
                objetivo_hora = _parse_hora(str(reserva_objetivo.get("hora") or ""))
                row_hora_obj = _parse_hora(str(row.get("hora") or ""))
                objetivo_cancha = str(reserva_objetivo.get("cancha") or "").strip().casefold()
                if objetivo_fecha and row_fecha_obj != objetivo_fecha:
                    continue
                if objetivo_hora and row_hora_obj != objetivo_hora:
                    continue
                if objetivo_cancha and self._cancha_row(row).strip().casefold() != objetivo_cancha:
                    continue

            idx_reserva = idx
            break

        if idx_reserva is None:
            print(f"[Calendario] No se encontró reserva activa para reprogramar: {telefono or nombre}")
            return False, (dia_texto, hora_texto, "")

        row = rows[idx_reserva]
        cancha = self._cancha_row(row)
        fecha_str = _fecha_a_str(fecha)
        hora_str = _hora_a_str(hora)
        duracion = row.get("duracion")

        # Guardar estado ORIGINAL
        estado_original = str(row.get("estado", "")).lower()
        senia_estado_original = str(row.get("senia_estado", "")).lower()
        senia_monto_original = row.get("senia_monto", "")

        print(f"[Calendario] ========================================")
        print(f"[Calendario] REPROGRAMACIÓN - Estado ORIGINAL:")
        print(f"[Calendario]   estado: {estado_original}")
        print(f"[Calendario]   senia_estado: {senia_estado_original}")
        print(f"[Calendario]   senia_monto: {senia_monto_original}")
        print(f"[Calendario]   cancha: {cancha}")
        print(f"[Calendario]   fecha original: {row.get('fecha')}")
        print(f"[Calendario]   hora original: {row.get('hora')}")
        print(f"[Calendario] NUEVA fecha/hora: {dia_texto} {hora_texto}")
        print(f"[Calendario] ========================================")

        # Verificar disponibilidad en la cancha del usuario
        cancha_actual_ocupada = False
        ocupante_info = None

        for idx, otra in enumerate(rows):
            if idx == idx_reserva:
                continue
            estado_otra = str(otra.get("estado", "")).lower()
            if estado_otra not in ACTIVE_BOOKING_STATUSES:
                continue
            otra_fecha, _ = _extraer_fecha_hora_de_row(otra)
            otra_hora = otra.get("hora", "")
            otra_cancha = self._cancha_row(otra)

            if (
                otra_fecha
                and _fecha_a_str(otra_fecha) == fecha_str
                and otra_hora == hora_str
                and otra_cancha == cancha
            ):
                otra_telefono = str(otra.get("telefono", "")).strip()
                otra_nombre = str(otra.get("nombre", "")).strip().lower()
                misma_persona = (
                    bool(telefono_buscar and otra_telefono == telefono_buscar)
                    or bool(nombre_buscar and otra_nombre == nombre_buscar)
                )

                if misma_persona:
                    # CORREGIDO: Solo si es EXACTAMENTE el mismo día, hora y cancha
                    # y del mismo contacto, entonces es un duplicado REAL
                    print(f"[Calendario] Duplicado REAL del mismo contacto a {hora_str} en {cancha}")
                    rows.pop(idx)
                    # Releer después de eliminar
                    return self.reprogramar_reserva(telefono, nombre, dia_texto, hora_texto,
                                                   senia_estado_preservado, senia_monto_preservado)
                else:
                    cancha_actual_ocupada = True
                    ocupante_info = otra_nombre or otra_telefono
                    print(f"[Calendario] Cancha {cancha} ocupada a las {hora_str} por {ocupante_info}")
                    break

        # Si la cancha actual está ocupada, buscar otra cancha a la MISMA hora
        if cancha_actual_ocupada:
            print(f"[Calendario] Cancha habitual {cancha} ocupada, buscando alternativa...")

            cancha_alternativa = None
            for court in COURTS:
                court_name = court["name"]
                if court_name == cancha:
                    continue

                ocupada = False
                for idx, otra in enumerate(rows):
                    if idx == idx_reserva:
                        continue
                    estado_otra = str(otra.get("estado", "")).lower()
                    if estado_otra not in ACTIVE_BOOKING_STATUSES:
                        continue
                    otra_fecha, _ = _extraer_fecha_hora_de_row(otra)
                    otra_hora = otra.get("hora", "")
                    otra_cancha = self._cancha_row(otra)
                    if (
                        otra_fecha
                        and _fecha_a_str(otra_fecha) == fecha_str
                        and otra_hora == hora_str
                        and otra_cancha == court_name
                    ):
                        ocupada = True
                        break

                if not ocupada:
                    cancha_alternativa = court_name
                    print(f"[Calendario] Encontrada cancha alternativa: {cancha_alternativa}")
                    break

            if cancha_alternativa:
                cancha = cancha_alternativa
                print(f"[Calendario] Usando cancha alternativa: {cancha}")
            else:
                alt_dia, alt_hora = self.proximo_slot_libre_desde(fecha, hora, cancha=cancha)
                print(f"[Calendario] Sin canchas libres a {hora_str}. Alternativa: {alt_dia} {alt_hora}")
                return False, (alt_dia, alt_hora, cancha)

        # Determinar nuevo estado basado en el ORIGINAL
        if senia_estado_original == "pagada":
            nuevo_senia_estado = "pagada"
            nuevo_senia_monto = senia_monto_original
            nuevo_estado = BOOKING_STATUS_RESERVED
            print(f"[Calendario] → Caso 1: Seña original PAGADA → manteniendo 'reservado'")
        elif senia_estado_preservado == "pagada":
            nuevo_senia_estado = "pagada"
            nuevo_senia_monto = senia_monto_preservado or senia_monto_original
            nuevo_estado = BOOKING_STATUS_RESERVED
            print(f"[Calendario] → Caso 2: Parámetro pide preservar seña pagada → 'reservado'")
        elif estado_original == BOOKING_STATUS_RESERVED:
            nuevo_senia_estado = senia_estado_original or "pagada"
            nuevo_senia_monto = senia_monto_original
            nuevo_estado = BOOKING_STATUS_RESERVED
            print(f"[Calendario] → Caso 3: Estado original 'reservado' → manteniendo 'reservado'")
        elif senia_estado_original == "pendiente":
            nuevo_senia_estado = "pendiente"
            nuevo_senia_monto = senia_monto_original
            nuevo_estado = BOOKING_STATUS_PENDING
            print(f"[Calendario] → Caso 4: Seña original 'pendiente' → manteniendo 'pendiente'")
        else:
            nuevo_senia_estado = senia_estado_original
            nuevo_senia_monto = senia_monto_original
            nuevo_estado = estado_original if estado_original in ACTIVE_BOOKING_STATUSES else BOOKING_STATUS_PENDING
            print(f"[Calendario] → Caso 5: Estado por defecto → {nuevo_estado}")

        # Actualizar la fila existente
        NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_mostrar = f"{NOMBRES_DIAS[fecha.weekday()]} {fecha.strftime('%d/%m/%Y')}"
        dia_corto = f"{NOMBRES_DIAS[fecha.weekday()]} {fecha.strftime('%d/%m')}"

        row["fecha"] = dia_mostrar
        row["hora"] = hora_str
        row["cancha"] = cancha
        row["duracion"] = duracion
        row["estado"] = nuevo_estado
        row["senia_estado"] = nuevo_senia_estado
        row["senia_monto"] = nuevo_senia_monto

        # ============================================================
        # CORREGIDO: SOLO eliminar duplicados que sean EXACTAMENTE
        # el mismo día, hora y cancha que el nuevo turno reprogramado
        # NO eliminar otros turnos válidos del mismo contacto
        # ============================================================
        duplicados_a_eliminar = []
        for idx, otra in enumerate(rows):
            if idx == idx_reserva:
                continue

            otra_fecha_raw = otra.get("fecha", "")
            otra_hora = otra.get("hora", "")
            otra_cancha = self._cancha_row(otra)

            # CORREGIDO: La condición para considerar duplicado es:
            # 1. Mismo contacto (por teléfono o nombre)
            # 2. MISMA fecha (comparar el día, no el string exacto)
            # 3. MISMA hora
            # 4. MISMA cancha
            otra_telefono = str(otra.get("telefono", "")).strip()
            otra_nombre = str(otra.get("nombre", "")).strip().lower()

            mismo_contacto = (
                (telefono_buscar and otra_telefono == telefono_buscar) or
                (nombre_buscar and otra_nombre == nombre_buscar)
            )

            if not mismo_contacto:
                continue

            # Extraer fecha de la otra reserva para comparar
            otra_fecha_obj, _ = _extraer_fecha_hora_de_row(otra)
            misma_fecha = otra_fecha_obj and _fecha_a_str(otra_fecha_obj) == fecha_str

            # CORREGIDO: Solo es duplicado si TODAS las condiciones coinciden
            if misma_fecha and otra_hora == hora_str and otra_cancha == cancha:
                duplicados_a_eliminar.append(idx)
                print(f"[Calendario] Duplicado REAL detectado: {otra.get('fecha')} {otra_hora} {otra_cancha}")
            else:
                # Este es un turno VÁLIDO del mismo contacto en otro horario
                print(f"[Calendario] Turno válido del mismo contacto (NO duplicado): {otra.get('fecha')} {otra_hora} {otra_cancha} - CONSERVADO")

        # Eliminar SOLO los duplicados reales
        for idx in sorted(duplicados_a_eliminar, reverse=True):
            dup = rows.pop(idx)
            print(f"[Calendario] Eliminado duplicado: {dup.get('fecha')} {dup.get('hora')} {dup.get('cancha')}")

        self._escribir_todos(rows)

        print(f"[Calendario] ========================================")
        print(f"[Calendario] REPROGRAMACIÓN EXITOSA:")
        print(f"[Calendario]   Contacto: {telefono or nombre}")
        print(f"[Calendario]   Nueva fecha: {dia_mostrar}")
        print(f"[Calendario]   Nueva hora: {hora_str}")
        print(f"[Calendario]   Cancha: {cancha}")
        print(f"[Calendario]   estado: {nuevo_estado}")
        print(f"[Calendario]   senia_estado: {nuevo_senia_estado}")
        print(f"[Calendario]   senia_monto: {nuevo_senia_monto}")
        print(f"[Calendario] ========================================")

        return True, (dia_corto, hora_str, cancha)


    def actualizar_senia(self, telefono: str, estado: str, monto: str = "") -> bool:
        if not telefono:
            return False

        rows = self._leer_todos()
        hoy = datetime.date.today()
        candidatas = []

        for idx, row in enumerate(rows):
            if row.get("telefono") != telefono:
                continue
            if str(row.get("estado", "")).lower() not in ACTIVE_BOOKING_STATUSES:
                continue

            fecha, hora = _extraer_fecha_hora_de_row(row)
            if fecha and fecha >= hoy:
                candidatas.append((fecha, hora or datetime.time.max, idx))
            elif not fecha:
                candidatas.append((datetime.date.max, datetime.time.max, idx))

        if not candidatas:
            return False

        candidatas.sort(key=lambda item: (item[0], item[1]))
        row = rows[candidatas[0][2]]
        row["senia_estado"] = estado or row.get("senia_estado", "")
        row["senia_monto"] = monto or row.get("senia_monto", "")
        self._escribir_todos(rows)
        print(f"[Calendario] Seña actualizada para {telefono}: {row['senia_estado']} {row.get('senia_monto', '')}")
        return True

    def actualizar_senia_reserva_especifica(
        self,
        reserva_objetivo: Dict[str, Any],
        estado: str,
        monto: str = "",
    ) -> bool:
        """Actualiza la seña de UNA reserva exacta, nunca la primera del contacto."""
        if not reserva_objetivo:
            return False
        with self.atomic():
            rows = self._leer_todos()
            objetivo_fecha = _texto_a_fecha(str(reserva_objetivo.get("fecha") or reserva_objetivo.get("dia") or ""))
            objetivo_hora = _parse_hora(str(reserva_objetivo.get("hora") or ""))
            objetivo_cancha = str(reserva_objetivo.get("cancha") or CANCHA_DEFAULT).strip().casefold()
            objetivo_tel = str(reserva_objetivo.get("telefono") or "").strip()
            objetivo_nombre = str(reserva_objetivo.get("nombre") or "").strip().casefold()

            matches = []
            for idx, row in enumerate(rows):
                if str(row.get("estado") or "").strip().lower() not in ACTIVE_BOOKING_STATUSES:
                    continue
                row_fecha, row_hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)
                if objetivo_fecha and row_fecha != objetivo_fecha:
                    continue
                if objetivo_hora and row_hora != objetivo_hora:
                    continue
                if objetivo_cancha and self._cancha_row(row).strip().casefold() != objetivo_cancha:
                    continue
                if objetivo_tel and str(row.get("telefono") or "").strip() != objetivo_tel:
                    continue
                if not objetivo_tel and objetivo_nombre and str(row.get("nombre") or "").strip().casefold() != objetivo_nombre:
                    continue
                matches.append(idx)

            if len(matches) != 1:
                return False
            row = rows[matches[0]]
            row["estado"] = BOOKING_STATUS_RESERVED if str(estado or "").lower() == "pagada" else row.get("estado", "")
            row["senia_estado"] = estado or row.get("senia_estado", "")
            row["senia_monto"] = monto or row.get("senia_monto", "")
            self._escribir_todos(rows)
            return True

    def cancelar_reserva_especifica(self, reserva_objetivo: Dict[str, Any]) -> dict:
        """Cancela exactamente una reserva identificada por fecha/hora/cancha/contacto."""
        if not reserva_objetivo:
            return {"ok": False, "motivo": "sin_objetivo"}
        with self.atomic():
            return self.cancelar_admin(
                dia_texto=str(reserva_objetivo.get("fecha") or reserva_objetivo.get("dia") or ""),
                hora_texto=str(reserva_objetivo.get("hora") or ""),
                telefono=str(reserva_objetivo.get("telefono") or ""),
                nombre=str(reserva_objetivo.get("nombre") or ""),
                cancha=str(reserva_objetivo.get("cancha") or ""),
            )

    def recuperar_contexto_por_contacto(self, telefono: str = "", nombre: str = "") -> dict:
        """
        Recupera contexto desde calendario_turnos.csv aunque la memoria conversacional se haya perdido.
        Prioriza reservas activas futuras; si no hay, devuelve canceladas futuras/recientes como candidatas.
        """
        telefono = str(telefono or "").strip()
        nombre = str(nombre or "").strip()
        nombre_norm = nombre.casefold()
        aliases_tel = {telefono} if telefono else set()
        if nombre:
            aliases_tel.add(f"NOMBRE:{nombre}")
        if telefono.startswith("NOMBRE:"):
            nombre_desde_tel = telefono.replace("NOMBRE:", "", 1).strip()
            if nombre_desde_tel:
                nombre_norm = nombre_norm or nombre_desde_tel.casefold()
                aliases_tel.add(f"NOMBRE:{nombre_desde_tel}")

        hoy = datetime.date.today()
        ahora = datetime.datetime.now()
        candidatas = []

        for idx, row in enumerate(self._leer_todos()):
            row_tel = str(row.get("telefono") or "").strip()
            row_nombre = str(row.get("nombre") or "").strip()
            pertenece = bool(row_tel and row_tel in aliases_tel)
            if not pertenece and nombre_norm:
                pertenece = row_nombre.casefold() == nombre_norm
            if not pertenece:
                continue

            fecha, hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)
            if fecha and hora and datetime.datetime.combine(fecha, hora) < ahora:
                continue
            if fecha and fecha < hoy:
                continue

            estado = str(row.get("estado") or "").strip().lower()
            senia_estado = str(row.get("senia_estado") or "").strip().lower()
            es_activa = estado in ACTIVE_BOOKING_STATUSES
            es_recuperable = estado == BOOKING_STATUS_CANCELLED.lower() and senia_estado in ("pendiente", "pagada")
            if not es_activa and not es_recuperable:
                continue

            prioridad_estado = 0 if es_activa else 1
            prioridad_senia = 0 if senia_estado == "pendiente" else 1
            candidatas.append({
                "idx": idx,
                "row": dict(row),
                "fecha": fecha,
                "hora": hora,
                "prioridad": (
                    prioridad_estado,
                    prioridad_senia,
                    fecha or datetime.date.max,
                    hora or datetime.time.max,
                ),
                "activa": es_activa,
                "recuperable": es_recuperable,
            })

        candidatas.sort(key=lambda item: item["prioridad"])
        if not candidatas:
            print(f"   🧠 [Contexto CSV] Sin candidatos para {telefono or nombre}")
            return {"ok": False, "motivo": "sin_contexto", "candidatas": []}

        print(
            f"   🧠 [Contexto CSV] {len(candidatas)} candidato(s) para {telefono or nombre}: "
            + " | ".join(
                f"{c['row'].get('fecha')} {c['row'].get('hora')} {c['row'].get('estado')} seña:{c['row'].get('senia_estado')}"
                for c in candidatas[:3]
            )
        )
        return {
            "ok": len(candidatas) == 1,
            "motivo": "unico" if len(candidatas) == 1 else "multiples",
            "reserva": candidatas[0]["row"] if len(candidatas) == 1 else None,
            "candidatas": [c["row"] for c in candidatas],
        }

    def aplicar_senia_a_reserva_recuperada(self, reserva: dict, estado: str = "pagada", monto: str = "") -> bool:
        if not reserva:
            return False

        rows = self._leer_todos()
        for row in rows:
            misma_reserva = (
                str(row.get("fecha") or "") == str(reserva.get("fecha") or "")
                and str(row.get("hora") or "") == str(reserva.get("hora") or "")
                and str(row.get("telefono") or "") == str(reserva.get("telefono") or "")
                and str(row.get("nombre") or "") == str(reserva.get("nombre") or "")
                and self._cancha_row(row) == (reserva.get("cancha") or CANCHA_DEFAULT)
            )
            if not misma_reserva:
                continue

            row["estado"] = BOOKING_STATUS_RESERVED
            row["senia_estado"] = estado or row.get("senia_estado", "")
            row["senia_monto"] = monto or row.get("senia_monto", "")
            self._escribir_todos(rows)
            print(
                "[Calendario] Contexto recuperado y seña aplicada: "
                f"{row.get('fecha')} {row.get('hora')} {row.get('cancha')} "
                f"para {row.get('nombre') or row.get('telefono')}"
            )
            return True

        return False

    def cancelar_por_dia_hora(self, dia_texto: str, hora_texto: str) -> bool:
        fecha = _texto_a_fecha(dia_texto)
        hora = _parse_hora(hora_texto)
        if not fecha or not hora:
            return False

        fecha_str = _fecha_a_str(fecha)
        hora_str = _hora_a_str(hora)

        rows = self._leer_todos()
        cambios = False
        for row in rows:
            row_fecha, _ = _extraer_fecha_hora_de_row(row)
            if (row_fecha and _fecha_a_str(row_fecha) == fecha_str and
                    row.get("hora") == hora_str):
                row["estado"] = BOOKING_STATUS_CANCELLED
                cambios = True
        if cambios:
            self._escribir_todos(rows)
            print(f"[Calendario] Reserva cancelada: {dia_texto} {hora_texto}")
        return cambios

    def cancelar(self, telefono: str) -> bool:
        rows = self._leer_todos()
        cambios = False
        for row in rows:
            if row.get("telefono") == telefono:
                row["estado"] = BOOKING_STATUS_CANCELLED
                cambios = True
        if cambios:
            self._escribir_todos(rows)
            print(f"[Calendario] Reserva cancelada para: {telefono}")
        return cambios

    def cancelar_por_contacto(self, telefono: str = "", nombre: str = "") -> dict:
        """
        Cancela solo reservas activas que pertenecen al contacto actual.
        La pertenencia se verifica por teléfono exacto o por nombre exacto normalizado.
        """
        telefono = str(telefono or "").strip()
        nombre_norm = str(nombre or "").strip().casefold()
        rows = self._leer_todos()
        hoy = datetime.date.today()
        candidatas = []

        for idx, row in enumerate(rows):
            if str(row.get("estado", "")).lower() not in ACTIVE_BOOKING_STATUSES:
                continue

            row_tel = str(row.get("telefono") or "").strip()
            row_nombre = str(row.get("nombre") or "").strip().casefold()
            pertenece = bool(telefono and row_tel == telefono)
            if not pertenece and nombre_norm:
                pertenece = row_nombre == nombre_norm
            if not pertenece:
                continue

            fecha, hora = _extraer_fecha_hora_de_row(row)
            if fecha and fecha < hoy:
                continue
            candidatas.append((fecha or datetime.date.max, hora or datetime.time.max, idx, row))

        if not candidatas:
            return {"ok": False, "motivo": "sin_reserva", "reservas": []}

        candidatas.sort(key=lambda item: (item[0], item[1]))
        if len(candidatas) > 1:
            return {
                "ok": False,
                "motivo": "multiples_reservas",
                "reservas": [item[3] for item in candidatas]
            }

        _, _, idx, reserva = candidatas[0]
        rows[idx]["estado"] = BOOKING_STATUS_CANCELLED
        self._escribir_todos(rows)
        print(
            "[Calendario] Reserva cancelada por contacto: "
            f"{reserva.get('fecha')} {reserva.get('hora')} {reserva.get('cancha')} "
            f"para {reserva.get('nombre') or reserva.get('telefono')}"
        )
        return {"ok": True, "motivo": "cancelada", "reserva": reserva}

    def cancelar_admin(
        self,
        dia_texto: str = "",
        hora_texto: str = "",
        telefono: str = "",
        nombre: str = "",
        cancha: str = ""
    ) -> dict:
        """
        Cancela reservas desde el panel autorizado. Permite identificar por fecha/hora,
        telefono, nombre y/o cancha. Si hay mas de una coincidencia, no cancela a ciegas.
        """
        fecha_obj = _texto_a_fecha(dia_texto) if dia_texto else None
        hora_obj = _parse_hora(hora_texto) if hora_texto else None
        telefono = str(telefono or "").strip()
        nombre_norm = str(nombre or "").strip().casefold()
        cancha_norm = str(cancha or "").strip().casefold()

        rows = self._leer_todos()
        candidatas = []
        for idx, row in enumerate(rows):
            if str(row.get("estado", "")).lower() not in ACTIVE_BOOKING_STATUSES:
                continue

            row_fecha, row_hora = _extraer_fecha_hora_de_row(row)
            if fecha_obj and row_fecha != fecha_obj:
                continue
            if hora_obj and row_hora != hora_obj:
                continue
            if telefono and str(row.get("telefono") or "").strip() != telefono:
                continue
            if nombre_norm and str(row.get("nombre") or "").strip().casefold() != nombre_norm:
                continue
            if cancha_norm and self._cancha_row(row).strip().casefold() != cancha_norm:
                continue

            candidatas.append((idx, row))

        if not candidatas:
            return {"ok": False, "motivo": "sin_reserva", "reservas": []}

        if len(candidatas) > 1:
            return {
                "ok": False,
                "motivo": "multiples_reservas",
                "reservas": [row for _, row in candidatas]
            }

        idx, reserva = candidatas[0]
        rows[idx]["estado"] = BOOKING_STATUS_CANCELLED
        self._escribir_todos(rows)
        print(
            "[Calendario] Reserva cancelada por admin: "
            f"{reserva.get('fecha')} {reserva.get('hora')} {reserva.get('cancha')} "
            f"para {reserva.get('nombre') or reserva.get('telefono')}"
        )
        return {"ok": True, "motivo": "cancelada", "reserva": reserva}

    def obtener_reserva_por_telefono(self, telefono: str, nombre: str = None) -> Optional[Dict]:
        """
        Obtiene la reserva activa de un contacto por teléfono o nombre.
        Lee directamente del CSV sin usar SQLite.
        """
        if not telefono and not nombre:
            return None

        rows = self._leer_todos()
        ahora = datetime.datetime.now()
        candidatas = []

        def agregar_si_vigente(row: dict, motivo: str) -> None:
            estado = str(row.get("estado", "")).lower()
            if estado not in ACTIVE_BOOKING_STATUSES:
                return
            fecha, hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)
            if fecha and hora and datetime.datetime.combine(fecha, hora) < ahora:
                return
            if fecha and fecha < ahora.date():
                return
            candidatas.append((fecha or datetime.date.max, hora or datetime.time.max, dict(row), motivo))

        # Normalizar teléfono para comparación
        telefono_normalizado = str(telefono or "").strip()
        es_contacto_agendado = telefono_normalizado.startswith("NOMBRE:")

        if es_contacto_agendado:
            # Buscar por nombre (extraer el nombre del teléfono agendado)
            nombre_buscar = telefono_normalizado.replace("NOMBRE:", "").strip().lower()
            for row in rows:
                row_nombre = str(row.get("nombre", "")).strip().lower()
                if row_nombre == nombre_buscar:
                    agregar_si_vigente(row, "nombre")
        else:
            # Buscar por teléfono
            for row in rows:
                row_telefono = str(row.get("telefono", "")).strip()
                if row_telefono == telefono_normalizado:
                    agregar_si_vigente(row, "telefono")

        # Si no se encontró por teléfono y hay nombre, intentar por nombre
        if not candidatas and nombre and not es_contacto_agendado:
            nombre_buscar = str(nombre).strip().lower()
            for row in rows:
                row_nombre = str(row.get("nombre", "")).strip().lower()
                if row_nombre == nombre_buscar:
                    agregar_si_vigente(row, "nombre (fallback)")

        if candidatas:
            candidatas.sort(key=lambda item: (item[0], item[1]))
            _, _, reserva, motivo = candidatas[0]
            print(f"   🔍 [Calendario] Reserva encontrada por {motivo}: {reserva.get('telefono') or reserva.get('nombre')} -> {reserva.get('fecha')} {reserva.get('hora')} {reserva.get('cancha')}")
            return reserva

        print(f"   🔍 [Calendario] No se encontró reserva para: {telefono or nombre}")
        return None


    def obtener_reserva_por_nombre(self, nombre: str) -> Optional[Dict]:
        """
        Obtiene la reserva activa de un contacto por su nombre.
        Lee directamente del CSV sin usar SQLite.
        """
        if not nombre:
            return None

        rows = self._leer_todos()
        nombre_buscar = str(nombre).strip().lower()
        ahora = datetime.datetime.now()
        candidatas = []

        for row in rows:
            row_nombre = str(row.get("nombre", "")).strip().lower()
            if row_nombre == nombre_buscar:
                estado = str(row.get("estado", "")).lower()
                if estado in ACTIVE_BOOKING_STATUSES:
                    fecha, hora = _extraer_fecha_hora_de_row(row, asumir_proximo_anio_si_paso=False)
                    if fecha and hora and datetime.datetime.combine(fecha, hora) < ahora:
                        continue
                    if fecha and fecha < ahora.date():
                        continue
                    candidatas.append((fecha or datetime.date.max, hora or datetime.time.max, dict(row)))

        if candidatas:
            candidatas.sort(key=lambda item: (item[0], item[1]))
            _, _, reserva = candidatas[0]
            print(f"   🔍 [Calendario] Reserva encontrada por nombre: {reserva.get('nombre')} -> {reserva.get('fecha')} {reserva.get('hora')} {reserva.get('cancha')}")
            return reserva

        print(f"   🔍 [Calendario] No se encontró reserva para nombre: {nombre}")
        return None


    def listar_reservas(self) -> List[dict]:
        rows = self._leer_todos()
        activas = [r for r in rows if str(r.get("estado", "")).lower() in ACTIVE_BOOKING_STATUSES]
        activas = self._ordenar_filas(activas)
        return activas

    def proximas_reservas_str(self, limite: int = UPCOMING_BOOKINGS_LIMIT) -> str:
        reservas = self.listar_reservas()
        hoy = datetime.date.today()
        futuras = []
        for r in reservas:
            fecha, _ = _extraer_fecha_hora_de_row(r)
            if fecha and fecha >= hoy:
                futuras.append(r)

        futuras = futuras[:limite]
        if not futuras:
            return "Sin reservas próximas."
        lineas = []
        for r in futuras:
            lineas.append(f"• {r['fecha']} {r['hora']} — {r.get('nombre','?')} ({r.get('telefono','')})")
        return "\n".join(lineas)

    def _upsert_fila_slot(
        self,
        dia_str: str,
        hora_str: str,
        telefono: str,
        nombre: str = "",
        website: str = "",
        fecha_obj=None,
        hora_obj=None,
        cancha: str = None,
        estado: str = BOOKING_STATUS_RESERVED,
        senia_estado: str = "",
        senia_monto: str = "",
        extra_fields: Optional[Dict[str, Any]] = None
    ):
        """
        Busca una fila existente por (teléfono/nombre + fecha + hora + cancha) y la actualiza.
        Si no existe, inserta una fila nueva.
        Nunca toca filas de otros slots del mismo contacto.
        """
        cancha = cancha or CANCHA_DEFAULT
        fecha_str = _fecha_a_str(fecha_obj) if fecha_obj else None

        filas = self._leer_todos()
        actualizado = False

        for i, row in enumerate(filas):
            row_fecha, _ = _extraer_fecha_hora_de_row(row)
            row_fecha_str = _fecha_a_str(row_fecha) if row_fecha else None

            mismo_slot = (
                row_fecha_str == fecha_str
                and row.get("hora") == hora_str
                and self._cancha_row(row) == cancha
            ) if fecha_str else (
                row.get("fecha") == dia_str
                and row.get("hora") == hora_str
                and self._cancha_row(row) == cancha
            )

            mismo_contacto = (
                (telefono and row.get("telefono") == telefono)
                or (nombre and row.get("nombre", "").lower() == nombre.lower())
            )

            if mismo_slot and mismo_contacto:
                filas[i]["fecha"] = dia_str
                filas[i]["hora"] = hora_str
                filas[i]["telefono"] = telefono
                filas[i]["nombre"] = nombre or filas[i].get("nombre", "")
                filas[i]["website"] = website or filas[i].get("website", "")
                filas[i]["cancha"] = cancha
                filas[i]["estado"] = estado
                filas[i]["senia_estado"] = senia_estado
                filas[i]["senia_monto"] = senia_monto
                for key, value in (extra_fields or {}).items():
                    if key in FIELDNAMES:
                        filas[i][key] = value
                actualizado = True
                break

        if not actualizado:
            self._insertar_fila_nueva(
                dia_str, hora_str, telefono, nombre, website,
                fecha_obj=fecha_obj, hora_obj=hora_obj,
                cancha=cancha, estado=estado,
                senia_estado=senia_estado, senia_monto=senia_monto,
                extra_fields=extra_fields
            )
            return

        self._escribir_todos(filas)


    def _insertar_fila_nueva(
        self,
        dia_str: str,
        hora_str: str,
        telefono: str,
        nombre: str = "",
        website: str = "",
        fecha_obj=None,
        hora_obj=None,
        cancha: str = None,
        estado: str = BOOKING_STATUS_RESERVED,
        senia_estado: str = "",
        senia_monto: str = "",
        extra_fields: Optional[Dict[str, Any]] = None
    ):
        """
        Inserta una fila nueva en el CSV sin modificar ninguna fila existente.
        Se usa cuando el contacto reserva un slot diferente al que ya tenía.
        """
        cancha = cancha or CANCHA_DEFAULT
        nueva_fila = {
            "fecha": dia_str,
            "hora": hora_str,
            "telefono": telefono,
            "nombre": nombre,
            "website": website,
            "cancha": cancha,
            "estado": estado,
            "senia_estado": senia_estado,
            "senia_monto": senia_monto,
        }
        for key, value in (extra_fields or {}).items():
            if key in FIELDNAMES:
                nueva_fila[key] = value
        filas = self._leer_todos()
        if not str(nueva_fila.get("reservation_id") or "").strip():
            nueva_fila["reservation_id"] = self._next_reservation_id_unlocked(filas)
        filas.append(nueva_fila)
        self._escribir_todos(filas)


# V2.10: toda mutación pública/auxiliar conocida entra por el mismo lock.
# Esto evita lost updates entre reservas, cancelaciones, bloqueos, señas y tareas admin.
def _atomicize_calendar_method(method):
    if getattr(method, "_calendar_atomicized", False):
        return method
    def wrapped(self, *args, **kwargs):
        with self.atomic():
            return method(self, *args, **kwargs)
    wrapped.__name__ = getattr(method, "__name__", "atomic_method")
    wrapped.__doc__ = getattr(method, "__doc__", None)
    wrapped._calendar_atomicized = True
    return wrapped


for _calendar_mutator_name in (
    "_mover_terminadas",
    "bloquear_dia_completo",
    "desbloquear_dia_completo",
    "actualizar_senia",
    "actualizar_senia_reserva_especifica",
    "aplicar_senia_a_reserva_recuperada",
    "cancelar_por_dia_hora",
    "cancelar",
    "cancelar_por_contacto",
    "cancelar_admin",
    "_upsert_fila_slot",
    "_insertar_fila_nueva",
    "_escribir_todos",
):
    _method = getattr(CalendarioLlamadas, _calendar_mutator_name, None)
    if _method is not None:
        setattr(CalendarioLlamadas, _calendar_mutator_name, _atomicize_calendar_method(_method))



def main():
    parser = argparse.ArgumentParser(description='Gestión de calendario de llamadas')
    parser.add_argument('--order', action='store_true', 
                       help='Ordena el archivo CSV por fecha y hora y mueve las llamadas pasadas a terminadas')

    args = parser.parse_args()

    calendario = CalendarioLlamadas()

    if args.order:
        calendario.ordenar_y_limpiar_archivo()
        sys.exit(0)


if __name__ == "__main__":
    main()
