"""
Parser de tempo natural em português brasileiro.

Converte expressões como:
- "daqui 5 minutos" → timestamp +5min
- "amanhã às 8" → timestamp do dia seguinte 08:00
- "todo dia 22h" → recurrence cron-like
- "toda segunda 9h" → recurrence cron-like

Retorna (trigger_at, recurrence_str) onde recurrence vazio = one-shot.
"""

import re
from datetime import datetime, timedelta, time as dtime
from typing import Optional, Tuple


WEEKDAYS = {
    "domingo": 6, "dom": 6,
    "segunda": 0, "seg": 0,
    "terca": 1, "ter": 1, "terça": 1,
    "quarta": 2, "qua": 2,
    "quinta": 3, "qui": 3,
    "sexta": 4, "sex": 4,
    "sabado": 5, "sab": 5, "sábado": 5,
}

MONTHS = {
    "janeiro": 1, "jan": 1,
    "fevereiro": 2, "fev": 2,
    "marco": 3, "mar": 3, "março": 3,
    "abril": 4, "abr": 4,
    "maio": 5, "mai": 5,
    "junho": 6, "jun": 6,
    "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9,
    "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def _parse_hour(text: str) -> Optional[Tuple[int, int]]:
    """Procura hora no texto. Retorna (hora, minuto) ou None."""
    # 22h, 22h30, 22:30, 22:00, 22 horas
    m = re.search(r"(\d{1,2})[h:](\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*h(?:oras?)?", text)
    if m:
        return int(m.group(1)), 0
    m = re.search(r"as?\s+(\d{1,2})", text)
    if m:
        return int(m.group(1)), 0
    return None


def parse_time_expression(text: str, now: Optional[datetime] = None
                          ) -> Optional[Tuple[int, str]]:
    """
    Parser principal. Retorna (timestamp_unix, recurrence) ou None.

    recurrence == "" para one-shot.
    recurrence == "daily HH:MM" para diário.
    recurrence == "weekly N HH:MM" (N=0=segunda, 6=domingo).
    """
    if now is None:
        now = datetime.now()

    text = _normalize(text)

    # ---- Recorrente: "todo dia 22h" / "todos os dias 8h" ----
    if re.search(r"\b(todo dia|todos os dias|diariamente|toda manha|toda tarde|toda noite)\b", text):
        hm = _parse_hour(text)
        if hm is None:
            # default por contexto
            if "manha" in text or "manhã" in text:
                hm = (8, 0)
            elif "tarde" in text:
                hm = (15, 0)
            elif "noite" in text:
                hm = (20, 0)
            else:
                hm = (9, 0)
        h, m = hm
        # próximo trigger: hoje se ainda não passou, senão amanhã
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return int(target.timestamp()), f"daily {h:02d}:{m:02d}"

    # ---- Recorrente semanal: "toda segunda 9h" ----
    for word, dow in WEEKDAYS.items():
        if re.search(rf"\btoda[s]?\s+(?:as\s+)?{word}\b", text):
            hm = _parse_hour(text) or (9, 0)
            h, m = hm
            # próximo dia da semana
            days_ahead = (dow - now.weekday()) % 7
            if days_ahead == 0:
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if target <= now:
                    days_ahead = 7
                    target += timedelta(days=7)
            else:
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                target += timedelta(days=days_ahead)
            return int(target.timestamp()), f"weekly {dow} {h:02d}:{m:02d}"

    # ---- One-shot: "daqui X min/hora/dia" ----
    m = re.search(r"daqui\s+(\d+)\s*(min|minuto|minutos|m)\b", text)
    if m:
        delta = timedelta(minutes=int(m.group(1)))
        return int((now + delta).timestamp()), ""

    m = re.search(r"daqui\s+(\d+)\s*(h|hora|horas)\b", text)
    if m:
        delta = timedelta(hours=int(m.group(1)))
        return int((now + delta).timestamp()), ""

    m = re.search(r"daqui\s+(\d+)\s*(d|dia|dias)\b", text)
    if m:
        delta = timedelta(days=int(m.group(1)))
        return int((now + delta).timestamp()), ""

    # ---- "em X minutos" ----
    m = re.search(r"em\s+(\d+)\s*(min|minuto|minutos|m)\b", text)
    if m:
        delta = timedelta(minutes=int(m.group(1)))
        return int((now + delta).timestamp()), ""

    m = re.search(r"em\s+(\d+)\s*(h|hora|horas)\b", text)
    if m:
        delta = timedelta(hours=int(m.group(1)))
        return int((now + delta).timestamp()), ""

    # ---- "amanhã às 8" ----
    if "amanha" in text or "amanhã" in text:
        hm = _parse_hour(text) or (9, 0)
        h, m = hm
        target = (now + timedelta(days=1)).replace(
            hour=h, minute=m, second=0, microsecond=0
        )
        return int(target.timestamp()), ""

    # ---- "hoje às 22h" ----
    if "hoje" in text:
        hm = _parse_hour(text)
        if hm:
            h, m = hm
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)  # já passou, agenda pra amanhã
            return int(target.timestamp()), ""

    # ---- Próxima ocorrência de um dia da semana: "segunda 9h" ----
    for word, dow in WEEKDAYS.items():
        if re.search(rf"\b{word}\b", text):
            hm = _parse_hour(text) or (9, 0)
            h, m = hm
            days_ahead = (dow - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            target += timedelta(days=days_ahead)
            return int(target.timestamp()), ""

    # ---- Só uma hora: "às 22h" → hoje ou amanhã ----
    hm = _parse_hour(text)
    if hm:
        h, m = hm
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return int(target.timestamp()), ""

    return None


def next_recurrence(recurrence: str, now: Optional[datetime] = None
                    ) -> Optional[int]:
    """Calcula próximo trigger de uma recorrência conhecida."""
    if now is None:
        now = datetime.now()

    parts = recurrence.split()
    if not parts:
        return None

    if parts[0] == "daily" and len(parts) >= 2:
        # "daily HH:MM"
        try:
            h, m = map(int, parts[1].split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return int(target.timestamp())
        except Exception:
            return None

    if parts[0] == "weekly" and len(parts) >= 3:
        # "weekly DOW HH:MM"
        try:
            dow = int(parts[1])
            h, m = map(int, parts[2].split(":"))
            days_ahead = (dow - now.weekday()) % 7
            if days_ahead == 0:
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if target <= now:
                    days_ahead = 7
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            target += timedelta(days=days_ahead)
            return int(target.timestamp())
        except Exception:
            return None

    return None


def format_timestamp(ts: int) -> str:
    """Formata timestamp pra exibição amigável: '29/04 às 14:30'."""
    dt = datetime.fromtimestamp(ts)
    now = datetime.now()
    diff = (dt.date() - now.date()).days

    hora = dt.strftime("%H:%M")

    if diff == 0:
        return f"hoje às {hora}"
    if diff == 1:
        return f"amanhã às {hora}"
    if 0 < diff < 7:
        nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        return f"{nomes[dt.weekday()]} às {hora}"
    return dt.strftime("%d/%m às %H:%M")


def humanize_recurrence(rec: str) -> str:
    """Transforma 'daily 22:00' em 'todo dia às 22:00'."""
    parts = rec.split()
    if not parts:
        return "uma vez"
    if parts[0] == "daily" and len(parts) >= 2:
        return f"todo dia às {parts[1]}"
    if parts[0] == "weekly" and len(parts) >= 3:
        nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        try:
            dow = int(parts[1])
            return f"toda {nomes[dow]} às {parts[2]}"
        except Exception:
            return rec
    return rec
