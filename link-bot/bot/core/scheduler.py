"""Scheduler de lembretes - loop async em background.

A cada N segundos, verifica reminders due e dispara via callback.
Recorrentes são re-agendados; one-shot são marcados sent.
"""

import asyncio
import os
import time
import logging
from typing import Callable, Awaitable

from bot.core.reminder_art import (
    plain_reminder_text,
    reminder_caption,
    render_reminder_card,
    render_starwars_card,
)
from bot.core.timeparse import next_recurrence


log = logging.getLogger("scheduler")


class ReminderScheduler:
    """Loop assíncrono que dispara lembretes na hora certa."""

    def __init__(self, storage, send_fn: Callable[[str, str], Awaitable[None]],
                 check_interval: int = 30):
        """
        send_fn(user_jid, text) - função que entrega o lembrete.
        check_interval - segundos entre verificações.
        """
        self.storage = storage
        self.send_fn = send_fn
        self.check_interval = check_interval
        self._task = None
        self._running = False
        self._card_cache: dict[int, str] = {}
        self._prerendering: set[int] = set()

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("⏰ Scheduler de pergaminhos iniciado.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                log.error(f"Erro no scheduler: {e}")
            await asyncio.sleep(self.check_interval)

    async def _prerender_card(self, rid: int, reminder: dict):
        try:
            path = await render_starwars_card(reminder)
            self._card_cache[rid] = path
            log.info(f"Card Star Wars pré-renderizado #{rid}")
        except Exception as e:
            log.warning(f"Falha ao pré-renderizar #{rid}: {e}")
        finally:
            self._prerendering.discard(rid)

    async def _tick(self):
        now = int(time.time())

        # Pré-render 5 min antes do disparo
        upcoming = self.storage.reminder_due(now + 300)
        due_now_ids = {r["id"] for r in self.storage.reminder_due(now)}
        upcoming_ids = {r["id"] for r in upcoming}

        for r in upcoming:
            rid = r["id"]
            if rid not in due_now_ids and rid not in self._card_cache and rid not in self._prerendering:
                self._prerendering.add(rid)
                asyncio.create_task(self._prerender_card(rid, r))

        # Limpa cache de rids removidos da fila
        for rid in [r for r in list(self._card_cache) if r not in upcoming_ids]:
            path = self._card_cache.pop(rid, None)
            if path:
                try: os.remove(path)
                except Exception: pass

        due = self.storage.reminder_due(now)

        for r in due:
            user_jid = r["user_jid"]
            send_to = r.get("send_to") or ""
            text = r["text"]
            recurrence = r["recurrence"] or ""
            rid = r["id"]

            image_path = self._card_cache.pop(rid, None)
            if image_path is None:
                try:
                    image_path = await render_starwars_card(r)
                except Exception as e:
                    log.warning(f"Falha ao gerar card Star Wars #{rid}: {e}")
                    try:
                        image_path = render_reminder_card(r)
                    except Exception:
                        pass

            try:
                await self.send_fn(user_jid, reminder_caption(r), image_path, send_to=send_to)
                log.info(f"Disparei lembrete #{rid} pra {send_to or user_jid}")
            except Exception as e:
                log.error(f"Falha ao disparar imagem #{rid}: {e}")
                try:
                    await self.send_fn(user_jid, plain_reminder_text(r), None, send_to=send_to)
                    log.info(f"Disparei lembrete #{rid} como texto pra {send_to or user_jid}")
                except Exception as fallback_error:
                    log.error(f"Falha ao disparar #{rid}: {fallback_error}")
                    continue
            finally:
                if image_path:
                    try:
                        os.remove(image_path)
                    except FileNotFoundError:
                        pass
                    except Exception:
                        pass

            # Pós-disparo: recorrente ou one-shot?
            if recurrence:
                next_ts = next_recurrence(recurrence)
                if next_ts:
                    self.storage.reminder_reschedule(rid, next_ts)
                else:
                    self.storage.reminder_mark_sent(rid)
            else:
                self.storage.reminder_mark_sent(rid)
