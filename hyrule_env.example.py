"""
Template de credenciais do sistema Hyrule.
Copie este arquivo para hyrule_env.py e preencha com suas chaves reais.

    cp hyrule_env.example.py hyrule_env.py
"""

# Discord Bot — crie em https://discord.com/developers/applications
DISCORD_TOKEN = "SEU_DISCORD_BOT_TOKEN"

# OpenRouter — crie em https://openrouter.ai/keys (plano free disponivel)
OPENROUTER_KEYS = [
    "OPENROUTER_KEY_1",
    "OPENROUTER_KEY_2",   # opcional — 2a chave para rotacao
    "OPENROUTER_KEY_3",   # opcional — 3a chave para rotacao
]

# Cerebras — provider FAST do Link
CEREBRAS_KEYS = [
    "CEREBRAS_KEY_1",
    "CEREBRAS_KEY_2",   # opcional
    "CEREBRAS_KEY_3",   # opcional
]

# Mistral — provider QUALITY/chat antes do OpenRouter
MISTRAL_KEYS = [
    "MISTRAL_KEY_1",
    "MISTRAL_KEY_2",   # opcional
    "MISTRAL_KEY_3",   # opcional
]

# WhatsApp — numero do dono do bot (com DDI, sem + ou espacos)
# Exemplo: Brasil 55 + DDD 37 + numero = "WA_USER2_NUMBER"
WA_OWNER = "DDI_DDD_NUMERO"

# WhatsApp — lista de numeros autorizados a falar com o bot
WA_ALLOW_FROM = [
    "DDI_DDD_NUMERO_1",
    "DDI_DDD_NUMERO_2",
]

# Discord — ID do canal de grupo onde lembretes serão disparados (0 = usa DM)
# Para pegar o ID: Discord > Modo desenvolvedor > botão direito no canal > Copiar ID
DISCORD_REMINDER_CHANNEL_ID = 0
