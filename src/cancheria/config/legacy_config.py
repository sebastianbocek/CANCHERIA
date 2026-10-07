# -*- coding: utf-8 -*-
"""
Configuracion del agente turnero para canchas de futbol 5.
"""

import os
import re
from cancheria.paths import runtime_file
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# ================================
# CONFIGURACION API OPENAI
# ================================
OPENAI_API_KEY = ''  # El usuario puede configurarla desde configurador_cancheria.py

# ================================
# EMAIL NOTIFICATION CONFIG
# ================================
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "").strip()
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "").strip()
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "").strip()

# ================================
# NUMERO PRINCIPAL PARA CONTROL Y CONTACTO HUMANO (mantener como string)
# ================================
AUTHORIZED_NUMBER = os.getenv("AUTHORIZED_NUMBER", "").strip()

# Todos reciben una copia individual de cada alerta administrativa.
AUTHORIZED_NUMBERS = [x.strip() for x in os.getenv("AUTHORIZED_NUMBERS", AUTHORIZED_NUMBER).split(",") if x.strip()]

# ================================
# NUMEROS/NOMBRES AUTORIZADOS
# ================================
AUTHORIZED_NAMES = [x.strip() for x in os.getenv("AUTHORIZED_NAMES", "admin").split(",") if x.strip()]

# ================================
# CONFIGURACION DEL NEGOCIO
# ================================
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Complejo Deportivo CANCHERIA")
AGENT_NAME = os.getenv("AGENT_NAME", "Cancheria")
HUMAN_CONTACT_NAME = os.getenv("HUMAN_CONTACT_NAME", "Encargado")
HUMAN_WHATSAPP = os.getenv("HUMAN_WHATSAPP", AUTHORIZED_NUMBER)
HUMAN_AVAILABLE_HOURS = os.getenv("HUMAN_AVAILABLE_HOURS", "Horario a configurar")
HUMAN_DERIVATION_MESSAGE = "Te paso con el encargado al WhatsApp {human_whatsapp}"
BUSINESS_ADDRESS = os.getenv("BUSINESS_ADDRESS", "Dirección a configurar")
PAYMENT_ALIAS = os.getenv("PAYMENT_ALIAS", "ALIAS.A.CONFIGURAR")

COURTS = [{'name': 'Cancha 1', 'type': 'Futbol 5'},
 {'name': 'Cancha 2', 'type': 'Futbol 5'},
 {'name': 'Cancha 3', 'type': 'Tenis'},
 {'name': 'Cancha 4', 'type': 'Pádel'}]

# Servicios y elementos disponibles para los clientes.
# El agente consulta esta estructura como fuente de verdad; agregar o modificar
# servicios acá evita respuestas inventadas o conocimiento hardcodeado en el chat.
BUSINESS_SERVICES = [{'id': 'pelota_prestamo',
  'name': 'Pelota',
  'aliases': ['pelota', 'balón', 'balon'],
  'available': True,
  'loan_available': True,
  'notes': 'Hay una pelota disponible para prestar durante el turno.'}]

CON_QUINCHO = True

QUINCHOS = [{'name': 'Quincho 1', 'type': 'quincho/parrilla'},
 {'name': 'Quincho 2', 'type': 'quincho/parrilla'}]

QUINCHOS_PRICES = [{'description': 'Quincho 1', 'amount': '10000'}, {'description': 'Quincho 2', 'amount': '10000'}]

TURN_DURATION_MINUTES = 60
ARRIVAL_TOLERANCE_MINUTES = 10
REQUIRES_DEPOSIT = True
# Modalidades admitidas: "fixed" (monto fijo) o "percentage" (porcentaje
# sobre el precio total del turno). DEPOSIT_AMOUNT se conserva para la
# modalidad fija y para compatibilidad con configuraciones anteriores.
DEPOSIT_MODE = 'percentage'
DEPOSIT_AMOUNT = '$7500'
DEPOSIT_PERCENTAGE = 50
# 0 desactiva el minimo de anticipacion; los turnos ya iniciados no se reservan.
MIN_BOOKING_NOTICE_MINUTES = 0
MIN_CANCELLATION_NOTICE_MINUTES = 0
CANCELLATION_POLICY = 'No hay anticipacion minima para cancelar o reprogramar. La seña no se pierde automaticamente por cancelar cerca del inicio del turno.'

# ================================
# ALERTAS Y RECORDATORIOS
# ================================
OWNER_REMINDER_MINUTES_BEFORE = 15
CLIENT_REMINDER_MINUTES_BEFORE = 120
FINAL_OWNER_REMINDER_MINUTES_BEFORE = 5
DAILY_AGENDA_SUMMARY_TIME = '08:00'
POST_TURNO_FOLLOWUP_MINUTES = 5
# La propuesta de repetir el turno anterior es memoria temporal, no una fase.
# Después de este plazo deja de poder interceptar respuestas del cliente.
POST_TURNO_FOLLOWUP_TTL_HOURS = 24

# ================================
# PRECIOS
# ================================
PRICES = [{'description': 'Cancha 1', 'amount': '20000'},
 {'description': 'Cancha 2', 'amount': '20000'},
 {'description': 'Cancha 3', 'amount': '20000'},
 {'description': 'Cancha 4', 'amount': '20000'}]

# ================================
# DURACIONES DE TURNOS PERMITIDAS (en horas)
# ================================
ALLOWED_TURN_DURATIONS = [1.0, 1.5, 2.0]
DEFAULT_TURN_DURATION_HOURS = 1.0

# Precios por hora (NÚMERO, no string)
PRICE_PER_HOUR = 20000

# Calcular precios para diferentes duraciones (para usar en templates)
PRECIO_1_HORA = PRICE_PER_HOUR
PRECIO_1_5_HORAS = int(PRICE_PER_HOUR * 1.5)
PRECIO_2_HORAS = PRICE_PER_HOUR * 2

# Strings de precio para usar en el template
PRECIO_1_HORA_STR = f"${PRECIO_1_HORA:,}"
PRECIO_1_5_HORAS_STR = f"${PRECIO_1_5_HORAS:,}"
PRECIO_2_HORAS_STR = f"${PRECIO_2_HORAS:,}"

# Funciones de cálculo
def calcular_precio_total(horas: float) -> int:
    """Calcula el precio total según la cantidad de horas."""
    return int(PRICE_PER_HOUR * horas)

def calcular_monto_pendiente(precio_total: int, senia: int) -> int:
    """Calcula el monto pendiente después de restar la seña."""
    return max(0, precio_total - senia)


def calcular_senia_configurada(precio_total: int) -> int:
    """Calcula la seña vigente sobre el total real de una reserva."""
    if not REQUIRES_DEPOSIT:
        return 0

    try:
        total = max(0, int(precio_total or 0))
    except (TypeError, ValueError):
        total = 0

    modo = str(DEPOSIT_MODE or "fixed").strip().lower()
    if modo == "percentage":
        try:
            porcentaje = Decimal(str(DEPOSIT_PERCENTAGE).replace(",", "."))
            calculado = (Decimal(total) * porcentaje / Decimal("100")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
            return min(total, max(0, int(calculado)))
        except (InvalidOperation, TypeError, ValueError):
            return 0

    monto_limpio = re.sub(r"[^\d]", "", str(DEPOSIT_AMOUNT or ""))
    monto_fijo = int(monto_limpio) if monto_limpio else 0
    return min(total, max(0, monto_fijo)) if total else max(0, monto_fijo)


def descripcion_senia_configurada() -> str:
    """Descripción breve para prompts y panel de administración."""
    if str(DEPOSIT_MODE or "fixed").strip().lower() == "percentage":
        porcentaje = float(DEPOSIT_PERCENTAGE)
        etiqueta = f"{porcentaje:g}"
        return f"{etiqueta}% del total del turno"
    return DEPOSIT_AMOUNT or "sin seña configurada"

# ================================
# MENSAJE COMPLETO DE SOLICITUD DE SEÑA
# ================================
SENIA_REQUEST_MESSAGE = f"""Buenísimo, para dejar firme el turno necesito el comprobante de la seña de {{monto}} al alias {{alias}}.
Si tenés efectivo podés acercarte a {BUSINESS_ADDRESS} a reservar, gracias."""

# ================================
# CONFIGURACION CSV
# ================================
CSV_FILENAME = str(runtime_file("reservas_contactos.csv"))
CONTACTS_CSV = CSV_FILENAME
BOOKINGS_CSV = str(runtime_file("calendario_turnos.csv"))
FINISHED_BOOKINGS_CSV = str(runtime_file("turnos_terminados.csv"))
CALENDAR_DB_FILE = str(runtime_file("calendar_events.db"))
BOT_STATE_FILE = str(runtime_file("bot_state.pkl"))
CONVERSATION_LOG_FILE = str(runtime_file("conversation_log.jsonl"))
BOOKING_FIELDNAMES = [
    "reservation_id",
    "fecha",
    "hora",
    "estado",
    "telefono",
    "nombre",
    "cancha",
    "tipo_turno",
    "duracion_minutos",
    "duracion_horas",
    "precio",
    "precio_total",
    "con_quincho",
    "quincho",
    "quincho_hora_inicio",
    "quincho_hora_fin",
    "quincho_duracion_horas",
    "quincho_precio_hora",
    "quincho_precio_total",
    "senia_estado",
    "senia_monto",
    # La seña requerida y el dinero efectivamente recibido son conceptos
    # distintos. Estos campos permiten acumular varios comprobantes sin perder
    # el importe que todavía falta para confirmar el turno.
    "senia_pagada_monto",
    "senia_pendiente_monto",
    "senia_efectivo_pendiente",
    "payment_method",
    "monto_pendiente",
    "notas",
    "reservado_en",
]
CSV_FIELDS = [
    "Fecha", "Hora", "Duracion_Horas", "Hora_Fin",
    "Nombre", "Negocio", "Rubro",
    "Telefono", "Email", "Interes", "Estado",
    "Precio_Total", "Senia_Monto", "Monto_Pendiente",
    "Notas", "Conversacion", "Prioridad", "es cliente?"
]

# ================================
# CONFIGURACION DE TURNOS
# ================================
MAX_BOOKING_SEARCH_DAYS = 14
DEFAULT_COURT_NAME = COURTS[0]["name"] if COURTS else "Cancha 1"
DEFAULT_TURN_TYPE = "futbol 5"
DEFAULT_DEPOSIT_STATUS = "no_requiere"
BOOKING_STATUS_RESERVED = "reservado"
BOOKING_STATUS_PENDING = "pendiente"
BOOKING_STATUS_CANCELLED = "cancelado"
BOOKING_STATUS_CONFIRMED = "confirmado"
ACTIVE_BOOKING_STATUSES = [
    BOOKING_STATUS_RESERVED.lower(),
    BOOKING_STATUS_PENDING.lower(),
    BOOKING_STATUS_CONFIRMED.lower(),
    "",
]
UPCOMING_BOOKINGS_LIMIT = 5

# ================================
# CONFIGURACION OPERATIVA
# ================================
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "America/Argentina/Cordoba")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
SCHEDULER_CHECK_INTERVAL_SECONDS = 3
PAUSE_CONTROL_RECHECK_SECONDS = 120
QR_PREVENTIVE_REFRESH_INTERVAL_SECONDS = 900
QR_CHECK_INTERVAL_SECONDS = 10
QR_LOADING_RETRY_SECONDS = 5
QR_STUCK_RECOVERY_SECONDS = 180
QR_POST_LOGOUT_RECOVERY_SLEEP_SECONDS = 12
WA_DB_ERROR_AUTO_REPAIR = True
WA_DB_ERROR_MAX_REPAIR_ATTEMPTS = 2
BOT_DETECTION_THRESHOLD = 3
BOT_QUARANTINE_SECONDS = 3600
BOT_RESPONSE_TIME_THRESHOLD_SECONDS = 1.5

# ================================
# FRANJA DE ATENCION / TURNOS
# ================================
ATTENTION_DAYS = [0, 1, 2, 3, 4, 5, 6]

CALL_TIME_WINDOWS = [('10:00', '00:00')]

CALL_SLOT_DURATION_MINUTES = TURN_DURATION_MINUTES
CALL_DEFAULT_TIME = '20:00'
CALL_CONTEXT_DEFAULT_TIMES = {
    "a la mañana": "10:00",
    "a la manana": "10:00",
    "por la mañana": "10:00",
    "por la manana": "10:00",
    "mediodia": "13:00",
    "mediodía": "13:00",
    "tarde": "18:00",
    "noche": "21:00",
}

CALL_CONTEXT_SUGGESTIONS = {
    "a la mañana": ["10:00", "11:00"],
    "por la mañana": ["10:00", "11:00"],
    "tarde": ["18:00", "19:00"],
    "noche": ["20:00", "21:00", "22:00"],
    "mediodia": ["13:00", "14:00"],
    "mediodía": ["13:00", "14:00"],
}


def _hora_a_minutos(hora_str: str) -> int:
    hora, minuto = str(hora_str).strip().split(":")
    hora = int(hora)
    minuto = int(minuto)
    if hora < 0 or hora > 24 or minuto < 0 or minuto > 59 or (hora == 24 and minuto != 0):
        raise ValueError(f"Hora fuera de rango: {hora_str}")
    return hora * 60 + minuto


def _minutos_a_hora(total_minutos: int) -> str:
    hora = total_minutos // 60
    minuto = total_minutos % 60
    return f"{hora:02d}:{minuto:02d}"


NOMBRES_DIAS_ATENCION = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _normalizar_texto_dia(texto: str) -> str:
    texto = str(texto or "").lower().strip()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto


def _validar_dias_atencion_config(dias=None):
    validos = []
    for dia in ATTENTION_DAYS if dias is None else dias:
        try:
            dia_int = int(dia)
        except (TypeError, ValueError):
            continue
        if 0 <= dia_int <= 6 and dia_int not in validos:
            validos.append(dia_int)
    return validos


def obtener_dias_atencion():
    return _validar_dias_atencion_config()


def descripcion_dias_atencion() -> str:
    dias = obtener_dias_atencion()
    if not dias:
        return "sin dias configurados"
    if dias == [0, 1, 2, 3, 4, 5, 6]:
        return "lunes a domingo"
    ordenados = sorted(dias)
    if len(ordenados) >= 2 and ordenados == list(range(ordenados[0], ordenados[-1] + 1)):
        return f"{NOMBRES_DIAS_ATENCION[ordenados[0]]} a {NOMBRES_DIAS_ATENCION[ordenados[-1]]}"
    nombres = [NOMBRES_DIAS_ATENCION[dia] for dia in ordenados]
    return ", ".join(nombres)


def descripcion_atencion_mensaje() -> str:
    return f"{descripcion_dias_atencion()} de {descripcion_franjas_atencion_mensaje()}"


def validar_fecha_en_dias_atencion(fecha) -> bool:
    dias = obtener_dias_atencion()
    if not dias:
        return False
    if hasattr(fecha, "weekday"):
        return fecha.weekday() in dias
    texto = _normalizar_texto_dia(fecha)
    for idx, nombre in enumerate(NOMBRES_DIAS_ATENCION):
        if re.search(rf"\b{nombre}\b", texto):
            return idx in dias
    return True


def normalizar_hora_config(hora_str: str) -> str:
    if not hora_str:
        return ""
    texto = str(hora_str).strip()
    texto = re.sub(r"^(\d{1,2})\s+([0-5]\d)$", r"\1:\2", texto)
    if ":" not in texto:
        texto = f"{texto}:00"
    try:
        return _minutos_a_hora(_hora_a_minutos(texto))
    except Exception:
        return ""


def obtener_franjas_atencion_minutos():
    franjas = []
    for inicio, fin in CALL_TIME_WINDOWS:
        try:
            inicio_min = _hora_a_minutos(normalizar_hora_config(inicio))
            fin_min = _hora_a_minutos(normalizar_hora_config(fin))
            # En español el cierre de medianoche se configura como 00:00.
            # Operativamente es el límite 1440 del día que comenzó a la hora
            # de apertura, no un rango vacío ni un horario de 24:00 visible.
            if fin_min == 0 and inicio_min > 0:
                fin_min = 24 * 60
            if inicio_min < fin_min:
                franjas.append((inicio_min, fin_min))
        except Exception:
            continue
    return franjas


def obtener_hora_inicio_atencion() -> str:
    franjas = obtener_franjas_atencion_minutos()
    if not franjas:
        return "17:00"
    return _minutos_a_hora(min(inicio for inicio, _ in franjas))


def obtener_hora_cierre_atencion() -> str:
    franjas = obtener_franjas_atencion_minutos()
    if not franjas:
        return "23:59"
    cierre = _minutos_a_hora(max(fin for _, fin in franjas))
    return "00:00" if cierre == "24:00" else cierre


def descripcion_franjas_atencion() -> str:
    partes = []
    for inicio, fin in CALL_TIME_WINDOWS:
        inicio_norm = normalizar_hora_config(inicio)
        fin_norm = normalizar_hora_config(fin)
        if inicio_norm and fin_norm:
            partes.append(f"{inicio_norm} a {fin_norm}")
    return ", ".join(partes) if partes else "sin franjas configuradas"


def descripcion_franjas_atencion_mensaje() -> str:
    def _hora_para_mensaje(hora_norm: str, es_fin: bool = False) -> str:
        try:
            hora, minuto = hora_norm.split(":")
            if hora in {"00", "24"} and minuto == "00":
                return "00hs"
            if minuto == "00":
                return f"{int(hora)}hs"
            if es_fin and minuto == "59":
                return f"{hora_norm}hs"
            return f"{hora_norm}hs"
        except Exception:
            return f"{hora_norm}hs"

    partes = []
    for inicio, fin in CALL_TIME_WINDOWS:
        inicio_norm = normalizar_hora_config(inicio)
        fin_norm = normalizar_hora_config(fin)
        if inicio_norm and fin_norm:
            partes.append(f"{_hora_para_mensaje(inicio_norm)} a {_hora_para_mensaje(fin_norm, es_fin=True)}")
    return ", ".join(partes) if partes else "sin franjas configuradas"


def validar_hora_en_franja(hora_str: str) -> bool:
    hora_norm = normalizar_hora_config(hora_str)
    if not hora_norm:
        return False
    try:
        hora_min = _hora_a_minutos(hora_norm)
    except Exception:
        return False
    return any(inicio <= hora_min < fin for inicio, fin in obtener_franjas_atencion_minutos())


def obtener_primera_hora_atencion() -> str:
    for inicio, _ in obtener_franjas_atencion_minutos():
        return _minutos_a_hora(inicio)
    return CALL_DEFAULT_TIME


def obtener_hora_por_defecto(contexto: str = "") -> str:
    contexto_lower = str(contexto or "").lower()
    for palabra, hora in CALL_CONTEXT_DEFAULT_TIMES.items():
        if palabra in contexto_lower and validar_hora_en_franja(hora):
            return normalizar_hora_config(hora)
    if validar_hora_en_franja(CALL_DEFAULT_TIME):
        return normalizar_hora_config(CALL_DEFAULT_TIME)
    return obtener_primera_hora_atencion()


def formatear_hora_para_mensaje(hora_str: str) -> str:
    hora_norm = normalizar_hora_config(hora_str)
    if not hora_norm:
        return str(hora_str or "")
    hora, minuto = hora_norm.split(":")
    if hora in {"00", "24"} and minuto == "00":
        return "00hs"
    if minuto == "00":
        return f"{int(hora)}hs"
    return f"{hora_norm}hs"


def _ejemplos_validos_horario():
    ejemplos = []
    for inicio, fin in obtener_franjas_atencion_minutos():
        candidatos = [
            inicio,
            inicio + 60,
            inicio + ((fin - inicio) // 2),
            fin - CALL_SLOT_DURATION_MINUTES,
        ]
        for candidato in candidatos:
            if inicio <= candidato < fin:
                hora = _minutos_a_hora(candidato)
                if hora not in ejemplos:
                    ejemplos.append(hora)
            if len(ejemplos) >= 8:
                return ejemplos
    return ejemplos or [obtener_hora_por_defecto()]


def _ejemplos_invalidos_horario():
    franjas = obtener_franjas_atencion_minutos()
    if not franjas:
        return []
    primer_inicio = min(inicio for inicio, _ in franjas)
    ultimo_fin = max(fin for _, fin in franjas)
    ejemplos = []
    if primer_inicio >= 30:
        ejemplos.append(_minutos_a_hora(primer_inicio - 30))
    ejemplos.append(_minutos_a_hora(ultimo_fin))
    if ultimo_fin + 30 <= 24 * 60:
        ejemplos.append(_minutos_a_hora(ultimo_fin + 30))
    return ejemplos


def build_horarios_prompt_detallado() -> str:
    franja = descripcion_franjas_atencion_mensaje()
    dias = descripcion_dias_atencion()
    atencion = descripcion_atencion_mensaje()
    invalidos = ", ".join(_ejemplos_invalidos_horario())
    dur = TURN_DURATION_MINUTES

    duraciones_texto = ""
    if ALLOWED_TURN_DURATIONS:
        duraciones_desc = []
        for d in ALLOWED_TURN_DURATIONS:
            if d == 1.0:
                duraciones_desc.append(f"1 hora (${PRICE_PER_HOUR:,})")
            elif d == 1.5:
                duraciones_desc.append(f"1 hora y media (${int(PRICE_PER_HOUR * 1.5):,})")
            elif d == 2.0:
                duraciones_desc.append(f"2 horas (${PRICE_PER_HOUR * 2:,})")
            else:
                duraciones_desc.append(f"{d} horas")
        duraciones_texto = f"\n🕐 DURACIONES DE TURNOS PERMITIDAS: {', '.join(duraciones_desc)}.\n"

    return (
        "\nREGLA OBLIGATORIA - HORARIOS Y DURACIÓN DE TURNOS\n\n"
        f"Solo podes ofrecer turnos dentro de estos dias y esta franja configurada:\n"
        f"DIAS DE ATENCION: {dias}\n"
        f"FRANJA DE ATENCION: {franja}\n\n"
        f"Duracion base del turno: {dur} minutos.\n"
        f"{duraciones_texto}"
        "Reglas:\n"
        "- Antes de confirmar una reserva, detecta dia, hora, DURACIÓN y nombre de la persona.\n"
        "- Si el usuario pide 'hoy a la noche', interpreta la franja y ofrece una hora concreta dentro de la disponibilidad.\n"
        f"- Si el usuario da una hora dentro de la franja, aceptala como candidata y deja que el calendario confirme si esta libre.\n"
        "- Si el horario esta ocupado, ofrece una alternativa cercana.\n"
        "- Si todavia no dio hora, responde corto: 'Dale, que dia y horario queres reservar?'\n"
        "- No digas que hay disponibilidad si no fue validada por calendario.\n"
        f"- No ofrezcas turnos fuera de {atencion}.\n"
        f"- Si piden fuera de esos dias u horarios, informa que atendemos {atencion} y pregunta si desea reservar dentro de esos dias y horarios.\n"
        f"- Ejemplos invalidos: {invalidos}\n"
        "\n🕐 DETECCIÓN DE DURACIÓN:\n"
        "- 'una hora' o no especifica → duracion = 1.0\n"
        "- 'hora y media', '90 minutos' → duracion = 1.5\n"
        "- 'dos horas', '120 minutos' → duracion = 2.0\n"
        "- Si pide otra duración, decile que solo manejamos esos horarios y preguntale cuál le sirve.\n"
    )


def build_horarios_prompt_sistema() -> str:
    duraciones_texto = ""
    if ALLOWED_TURN_DURATIONS:
        duraciones_desc = []
        for d in ALLOWED_TURN_DURATIONS:
            if d == 1.0:
                duraciones_desc.append("1 hora")
            elif d == 1.5:
                duraciones_desc.append("1 hora y media")
            elif d == 2.0:
                duraciones_desc.append("2 horas")
            else:
                duraciones_desc.append(f"{d} horas")
        duraciones_texto = f" Los turnos pueden ser de {', '.join(duraciones_desc)}."

    return (
        f"- Solo podes ofrecer turnos dentro de: {descripcion_atencion_mensaje()}\n"
        f"- Duracion base de cada turno: {TURN_DURATION_MINUTES} minutos.{duraciones_texto}\n"
        f"- Precio por hora: ${PRICE_PER_HOUR:,}\n"
        "- Si el usuario da una hora valida, aceptala como candidata y deja que calendario confirme disponibilidad.\n"
        "- Si el usuario todavia no dio hora, pedi dia y horario de forma breve.\n"
        "- No inventes disponibilidad, precios ni promociones.\n"
        "- 🆕 Detectar duración: 'hora y media' → 1.5h, 'dos horas' → 2h, por defecto 1h.\n"
    )


HORARIOS_PROMPT_SISTEMA = build_horarios_prompt_sistema()

# ================================
# PROMPTS DE PRIMER CONTACTO
# ================================
SCRAPER_SYSTEM_PROMPT = (
    f"Sos {AGENT_NAME}, asistente de reservas de {BUSINESS_NAME}. "
    "Respondes consultas entrantes por WhatsApp para reservar canchas de futbol 5."
)

PROMPT_PRIMER_CONTACTO = """
Escribi una respuesta breve para una consulta entrante sobre turnos de futbol 5.
Objetivo: pedir dia y horario si falta informacion, o avanzar a reservar si ya esta claro.

Datos:
- Nombre del contacto: {nombre_negocio}
- Ubicacion: {ubicacion}
- Tiene sitio web: {tiene_web}
"""

# ================================
# DETECCIÓN DE INTENCIÓN DE RESERVA
# ================================
INTENT_DETECTION_PROMPT = """Sos un clasificador de intención de mensajes de WhatsApp.

Tu tarea es analizar el mensaje del usuario y determinar si el usuario está:
1. INICIANDO una conversación SIN intención clara de reservar (solo saludo, sin mencionar día, hora, cancha, o mostrar interés explícito).
2. QUERIENDO RESERVAR (menciona día, hora, cancha, "quiero reservar", "tenés turno", etc.)
3. RETOMANDO una conversación previa con un saludo corto (cuando ya hay historial y el usuario vuelve a saludar).

Respondé SOLO con JSON:
{
  "intencion": "saludo_sin_intencion" | "quiere_reservar" | "retomando_conversacion",
  "confianza": 0.0-1.0,
  "razon": "breve explicación"
}

Reglas:
- "saludo_sin_intencion": solo "hola", "buenas", "buen día", saludos aislados SIN pedir horarios, precios o mostrar interés en turno.
- "quiere_reservar": menciona día, hora, "reservar", "turno", "cancha", "jugar", "partido", pregunta por disponibilidad o precio.
- "retomando_conversacion": mensaje corto tipo "hola", "si", "ok" cuando YA hay historial de conversación previa.
"""


_PRINCIPIO_RECTOR_Y_PERSONALIDAD = """
╔══════════════════════════════════════════════════════════════════╗
║                    PRINCIPIO RECTOR DEL AGENTE                   ║
║                          RECEPCIONISTA IA                        ║
╚══════════════════════════════════════════════════════════════════╝

TU ROL: Sos el recepcionista de {business_name}. No sos un contestador automático.
Tu trabajo es agendar turnos de las diferentes canchas de forma rápida y eficiente.

⭐ PRINCIPIO RECTOR:
   "MI MISION ES AGENDAR TURNOS. SIEMPRE ARRANCO PREGUNTANDO DÍA Y HORARIO."

📋 REGLAS DE ORO:
   1. **PRIMER MENSAJE**: "🙋 ¡Hola! Soy {agent_name} de {business_name} 🏟️. ¿Qué día y horario querés reservar?"
   2. Si preguntan por horarios disponibles → OFRECÉ HORARIOS CONCRETOS (ej: "Para hoy tengo 17, 18, 19hs")
   3. Si dijeron "hoy" o "mañana" → USÁ ESO como día, no vuelvas a preguntarlo.
   4. Si TENÉS la información (horarios, dirección, precio) → RESPONDÉ DIRECTAMENTE.
   5. No repitas preguntas que ya fueron respondidas.
   6. Si falta información para reservar, pedí SOLO lo que falta.
   7. **CUANDO CONFIRMEN UN TURNO** → No informes precio total ni pidas reconfirmación. Si el turno ya quedó tomado, pedí foto del comprobante de la seña con el formato operativo configurado.

🕐 **REGLAS DE DURACIÓN (NUEVO):**
   - Los turnos pueden ser de 1 hora, 1 hora y media (90 min), o 2 horas (120 min).
   - Detectar la duración que quiere el usuario:
     * "hora y media", "90 minutos" → usa duración 1.5
     * "dos horas", "120 minutos" → usa duración 2.0
     * "una hora" o no especifica → usa duración 1.0
   - El precio se calcula automáticamente: ${price_per_hour} × duración
   - Ejemplo: 1 hora = {precio_1_hora_str}
   - Ejemplo: 1.5 horas = {precio_1_5_horas_str}
   - Ejemplo: 2 horas = {precio_2_horas_str}

REGLAS DE CONVERSION:
- **NUNCA inventes un día u hora que el usuario no mencionó.**
- **Si el usuario solo saludó** (ej: "hola", "buenas") y no hay historia previa de reserva, respondé presentándote y preguntando qué día y horario quiere.
- **Si el usuario ya tiene una reserva** y solo saluda, no asumas que quiere cambiar nada.
- **La única forma de confirmar un turno** es que el usuario diga explícitamente "sí", "dale", "ok", "reservame", "confirmo" o similar.

👤 DERIVACIÓN A HUMANO:
   Si el usuario pide explícitamente hablar con un humano o con el encargado:
   1. NO TE OFENDAS, es normal.
   2. Ofrecé el contacto del encargado: {human_contact_name} al {human_whatsapp}
   3. Avisá su horario de disponibilidad: {human_available_hours}
   4. Preguntá si querés que le avise que lo van a contactar.

🎭 TU PERSONALIDAD:
   - Sos eficiente, no hablás de más.
   - Te anticipás a las necesidades del cliente.
   - Si preguntan por horarios, los tirás rápidamente.
   - No hacés preguntas obvias.
   - Tonito canchero pero respetuoso, tipo recepcionista copado de un club.

🚫 LO QUE NO HACER:
   - Preguntar "¿qué día?" si ya lo dijeron.
   - Preguntar "¿qué horario?" si pidieron explícitamente que LES DIGAS los horarios.
   - Usar frases robóticas como "Estoy aquí para ayudarte" o "¿En qué puedo ayudarte?".
   - Hacerte el ofendido si piden hablar con un humano.
"""

_PROMPT_SETTER_TEMPLATE = _PRINCIPIO_RECTOR_Y_PERSONALIDAD + """\

Sos {agent_name}, asistente de reservas de {business_name}, una cancha de futbol 5.
Respondes WhatsApp de forma natural, corta y clara, con tono argentino informal. Usas "vos".

OBJETIVO PRINCIPAL:
Resolver rapido consultas entrantes y convertirlas en turnos reservados.

QUE PODES HACER:
- Informar precio si esta configurado (el precio varía según la duración).
- Consultar disponibilidad.
- Reservar turno (con duración variable).
- Reprogramar turno.
- Cancelar turno.
- Responder direccion, horarios, duracion del turno y reglas de seña.
- Derivar a una persona si el caso es raro o sensible (ver REGLAS DE DERIVACION).

DATOS DEL NEGOCIO:
- Nombre: {business_name}
- Precio por hora: ${price_per_hour:,}
- Direccion: {business_address}
- Contacto humano: {human_whatsapp} ({human_contact_name})
- Horario del humano: {human_available_hours}
- Canchas: {courts_str}
- Quincho/parrilla habilitado: {con_quincho_str}
- Quinchos/parrillas: {quinchos_str}
- Duracion base del turno: {turn_duration} minutos
- 🆕 Duraciones permitidas: 1h, 1.5h (90 min), 2h (120 min)
- Tolerancia de llegada: {arrival_tolerance} minutos
- Seña requerida: {requires_deposit}
- Monto de seña: {deposit_amount}
- Alias de pago: {payment_alias}
- Politica de cancelacion: {cancellation_policy}

CONTEXTO DE LA CONVERSACION:
- Fase actual: {{fase_actual}}
- Dia ya acordado: {{dia_previo}}
- Hora ya acordada: {{hora_previa}}
- 🆕 Duración ya acordada: {{duracion_previa}}

HISTORIAL RECIENTE:
{{historial_texto}}

ULTIMO MENSAJE DEL USUARIO:
"{{ultimo_mensaje}}"

DATOS DEL CONTACTO:
- Nombre: {{nombre}}
- Negocio: {{negocio}}
- Es cliente?: {{es_cliente}}

{{contexto_restriccion}}

{horarios_prompt}

REGLAS DE CONVERSACION:
1. **APLICA EL PRINCIPIO RECTOR:** Tu misión es agendar turnos. Siempre arrancá preguntando día y horario.
2. **PRIMER MENSAJE O SALUDO INICIAL:** Respondé "🙋 ¡Hola! Soy {agent_name} de {business_name} 🏟️. ¿Qué día y horario querés reservar?"
3. Si el usuario pregunta "qué horarios tenés disponibles" para un día específico, LISTÁ los horarios de la franja.
4. Si dice "hoy a la noche", "mañana tipo 8", "el viernes", resolve el dia/hora probable.
5. 🆕 **DETECTÁ LA DURACIÓN:** Si el usuario dice "hora y media", "90 minutos", "2 horas", usá esa duración para la reserva.
6. Si CON_QUINCHO está habilitado y pide quincho/parrilla/asador/tercer tiempo junto con un turno común, NO derives al encargado: tratá el quincho como complemento reservable por horas. "Tercer tiempo" es una forma común de pedir quincho/parrilla después del partido.
   Primero verificá disponibilidad de cancha para el día y horario pedido. Recién si hay cancha disponible, preguntá cuántas horas de quincho/parrilla quiere. No digas "te sumo" ni asignes un quincho específico antes de validar la cancha y conocer la duración del quincho.
   Cuando preguntes cuántas horas de quincho/parrilla quiere, aclarale que salvo que indique lo contrario se toma como inicio el mismo horario de la cancha. Si dice "después del partido" o similar, el quincho empieza cuando termina la cancha.
   Interpretá expresiones de contexto: "tercer tiempo" implica quincho después del partido; "hacer un asado antes" implica quincho antes de la cancha; "desde que llegamos" o "mientras jugamos" implica quincho desde el inicio de la cancha.
   Si CON_QUINCHO no está habilitado, no ofrezcas quincho/parrilla.
7. Solo deriva al encargado si pide evento grande, día completo, cumpleaños complejo, condiciones especiales o cerrar el predio.
8. Si falta el nombre para reservar, pedilo.
9. Si hay dia, hora, duración y nombre, marca tipo "confirmado" para que el sistema reserve.
10. Si el usuario quiere cancelar o reprogramar, ayudalo sin exigir anticipacion minima ni declarar perdida la seña por la cercania del turno.
11. Si pregunta precio → respondé según la duración que quiera (ej: "1 hora y media sale {precio_1_5_horas_str}") y seguí con la reserva.
12. No inventes canchas, quinchos, precios, promociones, torneos ni disponibilidad.
13. No uses frases roboticas como "Estoy aqui para ayudarte", "con gusto" o "¿En qué puedo ayudarte?".

🆕 REGLAS DE DERIVACION A HUMANO:
Si el usuario dice frases como:
- "Quiero hablar con un humano"
- "Poneme con el encargado"
- "Hablar con una persona"
- "Quiero hablar con el dueño"
- "No quiero hablar con un bot"
- "Pásame con alguien de verdad"

Entonces:
1. Respondé de forma natural: "Dale, te paso con {human_contact_name} al {human_whatsapp}. Está disponible {human_available_hours}. ¿Querés que le avise que lo contactás?"
2. Marcá tipo "derivar_humano" en el JSON.
3. No insistas en seguir con la reserva por tu cuenta.

No derives por quejas, insultos, ironías o frustración si no hay un pedido explícito de humano/encargado/persona. Ejemplo: "Para pasado mañana tenes? Sino cerra nomas tu mierda de cancha" sigue siendo una consulta de disponibilidad, no una derivación.

MANEJO DE CASOS FRECUENTES:
- **"Hola" (primer mensaje)** → Respondé: "🙋️ ¡Hola! Soy {agent_name} de {business_name} 🏟️. ¿Qué día y horario querés reservar?"
- **"Qué horarios tenés disponibles hoy?"** → Respondé: "Para hoy tengo: 17hs, 18hs, 19hs, 20hs, 21hs. ¿A qué hora querés?"
- **"Cuánto sale?"** → Respondé: "La hora está ${price_per_hour:,}. Si querés hora y media son {precio_1_5_horas_str} o 2 horas {precio_2_horas_str}. ¿Qué día y horario querés reservar?"
- **"Quiero reservar para mañana a las 19"** → Si está disponible y queda tomado, respondé con el pedido operativo de seña: "Buenísimo, para dejar firme el turno necesito foto del comprobante de la seña de {deposit_amount} al alias {payment_alias}. Si tenés efectivo podés acercarte a {business_address} a reservar, gracias."
- **"Quiero hablar con el encargado"** → Respondé: "Dale, te paso con {human_contact_name} al {human_whatsapp}. Está disponible {human_available_hours}. ¿Le aviso que lo contactás?"

TONO:
- Castellano argentino.
- Corto, practico, buena onda.
- Maximo 2 o 3 lineas salvo que haga falta explicar reglas.
- Emojis con mucha moderacion.

FORMATO JSON DE RESPUESTA (NUEVO con duración):
{{{{
    "tipo": "explicacion_pedida|duda|coordinacion_nueva|confirmacion_sin_hora|renegociacion|confirmado|no_interesado|post_confirmacion|otro|lista_horarios|derivar_humano",
    "dia_detectado": "hoy|mañana|lunes|martes|miercoles|jueves|viernes|sabado|domingo|null",
    "hora_detectada": "HH:MM o null",
    "duracion_detectada": 1.0|1.5|2.0|null,
    "nueva_fase": "inicial|duda_respondida|coordinacion_propuesta|coordinacion_confirmada|renegociando|derivado_humano",
    "razon": "1 linea explicando el analisis",
    "respuesta": "texto exacto a enviar, generado dinamicamente segun el contexto (vacio si tipo=confirmado)"
}}}}"""

# --- PASO 1: resolver variables estaticas del negocio ---
courts_str = ", ".join([f"{c['name']} - {c['type']}" for c in COURTS])
con_quincho_str = "si" if CON_QUINCHO else "no"
quinchos_str = ", ".join([f"{q['name']} - {q.get('type', 'quincho/parrilla')}" for q in QUINCHOS]) or "sin quinchos configurados"
requires_deposit_str = "si" if REQUIRES_DEPOSIT else "no"
deposit_amount_str = descripcion_senia_configurada()
price_str = f"${PRICE_PER_HOUR:,} la hora"
price_per_hour = PRICE_PER_HOUR
precio_1_hora_str = PRECIO_1_HORA_STR
precio_1_5_horas_str = PRECIO_1_5_HORAS_STR
precio_2_horas_str = PRECIO_2_HORAS_STR
horarios_prompt = build_horarios_prompt_detallado()

PROMPT_SETTER = _PROMPT_SETTER_TEMPLATE.format(
    agent_name=AGENT_NAME,
    business_name=BUSINESS_NAME,
    business_address=BUSINESS_ADDRESS,
    human_whatsapp=HUMAN_WHATSAPP,
    human_contact_name=HUMAN_CONTACT_NAME,
    human_available_hours=HUMAN_AVAILABLE_HOURS,
    courts_str=courts_str,
    con_quincho_str=con_quincho_str,
    quinchos_str=quinchos_str,
    price=price_str,
    price_per_hour=price_per_hour,
    PRICE_PER_HOUR=PRICE_PER_HOUR,
    precio_1_hora_str=precio_1_hora_str,
    precio_1_5_horas_str=precio_1_5_horas_str,
    precio_2_horas_str=precio_2_horas_str,
    turn_duration=TURN_DURATION_MINUTES,
    arrival_tolerance=ARRIVAL_TOLERANCE_MINUTES,
    requires_deposit=requires_deposit_str,
    deposit_amount=deposit_amount_str,
    payment_alias=PAYMENT_ALIAS,
    cancellation_policy=CANCELLATION_POLICY,
    horarios_prompt=horarios_prompt,
)


# ================================
# FUNCION: RESPUESTA DE CIERRE DE COORDINACION
# ================================
def build_confirmation_message(
    dia_resuelto: str = None,
    hora: str = None,
    cancha: str = None,
    duracion_horas: float = None,
    precio_total: int = None,
    senia_valor: int = None,
    monto_pendiente: int = None,
    senia_estado: str = ""
) -> str:
    """
    Construye el mensaje de confirmación de reserva.

    🔧 CORREGIDO: Maneja correctamente senia_valor cuando es None o string.
    """
    dia_str = dia_resuelto or "el dia acordado"
    hora_str = f" a las {formatear_hora_para_mensaje(hora)}" if hora else ""
    cancha_str = f"\nCancha: {cancha}" if cancha else ""

    duracion_texto = ""
    if duracion_horas:
        if duracion_horas == 1.0:
            duracion_texto = f"\n⏱️ Duración: 1 hora"
        elif duracion_horas == 1.5:
            duracion_texto = f"\n⏱️ Duración: 1 hora y media (90 minutos)"
        elif duracion_horas == 2.0:
            duracion_texto = f"\n⏱️ Duración: 2 horas (120 minutos)"
        else:
            duracion_texto = f"\n⏱️ Duración: {duracion_horas} horas"

    precios_texto = ""
    if precio_total is not None:
        if senia_valor is not None and monto_pendiente is not None:
            precios_texto = (
                f"\n💰 Precio total: ${precio_total:,}"
                f"\n💵 Seña: ${senia_valor:,}"
                f"\n💸 Saldo pendiente: ${monto_pendiente:,}"
            )
        else:
            precios_texto = f"\n💰 Precio total: ${precio_total:,}"

    # 🔧 CORRECCIÓN CRÍTICA: Manejar senia_valor cuando es None o string
    senia = ""
    if REQUIRES_DEPOSIT:
        if senia_estado == "pagada":
            # Intentar mostrar el monto de forma segura
            if senia_valor is not None:
                try:
                    # Si es número, formatear con comas
                    if isinstance(senia_valor, (int, float)):
                        senia = f"\n\n✅ Seña registrada: ${senia_valor:,.0f}."
                    else:
                        # Si es string, limpiar y mostrar
                        monto_limpio = re.sub(r'[^\d]', '', str(senia_valor))
                        if monto_limpio:
                            senia = f"\n\n✅ Seña registrada: ${int(monto_limpio):,}."
                        else:
                            senia = "\n\n✅ Seña registrada."
                except (ValueError, TypeError):
                    senia = "\n\n✅ Seña registrada."
            else:
                senia = "\n\n✅ Seña registrada."
        elif senia_estado == "pago_en_cancha":
            senia = "\n\n💰 Anoto que pagan en efectivo/en la cancha."
        else:
            # Estado pendiente o sin estado
            if isinstance(senia_valor, (int, float)) and senia_valor:
                senia_valor_str = f"${senia_valor:,}"
            elif precio_total is not None:
                senia_valor_str = f"${calcular_senia_configurada(precio_total):,}"
            else:
                senia_valor_str = descripcion_senia_configurada()
            senia = (
                f"\n\nBuenísimo, para dejar firme el turno necesito foto del comprobante de la seña de {senia_valor_str} "
                f"al alias {PAYMENT_ALIAS}."
                f"\nSi tenés efectivo podés acercarte a {BUSINESS_ADDRESS} a reservar, gracias."
            )

    return (
        f"✅ Listo, queda reservado para {dia_str}{hora_str}.\n"
        f"Te esperamos en {BUSINESS_NAME}.{cancha_str}"
        f"{duracion_texto}"
        f"{precios_texto}"
        f"{senia}\n\n"
        f"📌 Si necesitan cambiar o cancelar, avisen con tiempo por este WhatsApp."
    )


# ================================
# FUNCION: RESPUESTA DE DERIVACION A HUMANO
# ================================
def build_human_derivation_message() -> str:
    """Genera el mensaje para derivar al humano."""
    return HUMAN_DERIVATION_MESSAGE.format(
        human_contact_name=HUMAN_CONTACT_NAME,
        human_whatsapp=HUMAN_WHATSAPP,
        human_available_hours=HUMAN_AVAILABLE_HOURS
    )
