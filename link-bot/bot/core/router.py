"""
Router de comandos - matcher por palavra-chave natural.

Cada skill registra triggers (palavras/expressões que ativam ela).
O router pega a mensagem do OWNER, testa contra todos os triggers,
e dispara a skill com maior score.
"""

import re
from typing import Callable, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class Skill:
    """Uma skill registrada no router."""
    name: str                           # identificador único
    description: str                    # pra menu /ajuda
    triggers: List[str]                 # palavras-chave que ativam
    handler: Callable                   # async fn(ctx, args) -> resposta
    category: str = "geral"             # pra organizar no menu
    requires_media: bool = False        # se precisa de imagem/vídeo anexo
    enabled: bool = True                # liga/desliga
    priority: int = 0                   # desempate (maior ganha)


class Router:
    """
    Registra skills e roteia mensagens.

    Match natural: 'Link, qual o clima em POA' → skill 'clima' (trigger 'clima')
    """

    def __init__(self):
        self.skills: List[Skill] = []
        # palavras "vocativas" do bot, ignoradas no matching
        self.vocatives = {
            "link", "ei", "oi", "olá", "ola", "hey",
            "parceiro", "amigo", "guerreiro", "por", "favor", "pf",
            "você", "voce", "vc", "tu",
        }

    def register(self, skill: Skill):
        """Adiciona skill ao router."""
        self.skills.append(skill)
        # ordena por prioridade desc pra desempate
        self.skills.sort(key=lambda s: -s.priority)

    def normalize(self, text: str) -> str:
        """Lowercase, remove acentos comuns, remove pontuação leve."""
        text = text.lower().strip()
        # remove acentos comuns sem importar unidecode
        substitutions = str.maketrans(
            "áàâãäéèêëíìîïóòôõöúùûüç",
            "aaaaaeeeeiiiiooooouuuuc"
        )
        text = text.translate(substitutions)
        # remove pontuação
        text = re.sub(r"[^\w\s]", " ", text)
        # colapsa espaços
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def match(self, message: str) -> Optional[Tuple[Skill, str]]:
        """
        Retorna (skill, resto_da_mensagem) ou None.

        resto_da_mensagem = o que sobrou depois de remover trigger e vocativos
        (útil pra extrair argumentos: 'clima POA' → resto='poa')
        """
        norm = self.normalize(message)
        words = set(norm.split())

        # Remove vocativos pra não interferirem
        content_words = words - self.vocatives

        best_match = None
        best_score = 0
        best_trigger = None

        msg_lower = message.lower().strip()

        for skill in self.skills:
            if not skill.enabled:
                continue

            for trigger in skill.triggers:
                # Trigger com ! ou [ → match por prefixo exato
                if trigger.startswith("!") or trigger.startswith("["):
                    t_low = trigger.lower()
                    if msg_lower == t_low or msg_lower.startswith(t_low + " ") or msg_lower.startswith(t_low + ":"):
                        score = 50 + skill.priority
                        if score > best_score:
                            best_score = score
                            best_match = skill
                            best_trigger = t_low
                    continue

                trigger_norm = self.normalize(trigger)
                trigger_words = set(trigger_norm.split())

                # Se trigger é multi-palavra, exige todas presentes
                if len(trigger_words) > 1:
                    if trigger_words.issubset(words):
                        score = len(trigger_words) * 10 + skill.priority
                        if score > best_score:
                            best_score = score
                            best_match = skill
                            best_trigger = trigger_norm
                # Trigger única: bate se palavra inteira aparece
                else:
                    word = trigger_norm
                    if word in content_words:
                        score = 5 + skill.priority
                        if score > best_score:
                            best_score = score
                            best_match = skill
                            best_trigger = word

        if best_match is None:
            return None

        # Para triggers ! e [ → extrai resto a partir do texto original
        if best_trigger and (best_trigger.startswith("!") or best_trigger.startswith("[")):
            raw_lower = message.strip()
            prefix = best_trigger
            if raw_lower.lower().startswith(prefix):
                rest = raw_lower[len(prefix):].lstrip(" :").strip()
            else:
                rest = ""
        else:
            # Extrai "resto" — o que sobra depois de tirar vocativos e trigger
            rest_words = norm.split()
            trigger_tokens = best_trigger.split() if best_trigger else []
            rest_words = [
                w for w in rest_words
                if w not in self.vocatives and w not in trigger_tokens
            ]
            rest = " ".join(rest_words).strip()

        return (best_match, rest)

    def get_by_name(self, name: str) -> Optional[Skill]:
        for s in self.skills:
            if s.name == name:
                return s
        return None

    def list_enabled(self) -> List[Skill]:
        return [s for s in self.skills if s.enabled]

    def list_by_category(self) -> dict:
        """Retorna {categoria: [skills]} pra montar menu."""
        cats = {}
        for s in self.list_enabled():
            cats.setdefault(s.category, []).append(s)
        return cats
