import os
import time
import json
import logging
import asyncio
import aiohttp
import discord
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from views import ContribuirView


# === Variáveis de ambiente ===
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not DISCORD_TOKEN or not YOUTUBE_API_KEY:
    print("❌ DISCORD_TOKEN ou YOUTUBE_API_KEY não definidos no .env. O bot não pode iniciar.")
    exit(1)

# === Configuração ===
STATE_FILE = "stream_state.json"
STATE_BACKUP_FILE = "stream_state_backup.json"
CHANNELS_FILE = "channels.json"
LOG_FILE = "bot.log"
RESEND_INTERVAL_MINUTES = int(os.getenv("RESEND_INTERVAL_MINUTES", "10"))
RESEND_INTERVAL = RESEND_INTERVAL_MINUTES * 60
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
CHECK_INTERVAL = CHECK_INTERVAL_MINUTES * 60
GROUP_SIZE = int(os.getenv("CHECK_GROUP_SIZE", "3"))  # Quantos canais verificar por ciclo
GROUP_DELAY = int(os.getenv("CHECK_GROUP_DELAY", "180"))  # Atraso entre cada grupo de canais (em segundos)

# === Logging ===
log = logging.getLogger("RaceNotify")
log.setLevel(logging.INFO)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
console = logging.StreamHandler()
console.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
log.addHandler(file_handler)
log.addHandler(console)

# === Canais ===
YOUTUBE_CHANNEL_IDS = []
with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)
    YOUTUBE_CHANNEL_IDS = data.get("youtube_channel_ids", [])

# === Estado ===
def load_stream_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Erro ao carregar {STATE_FILE}: {e}")
    return {}

def save_stream_state(state):
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as original:
                with open(STATE_BACKUP_FILE, "w", encoding="utf-8") as backup:
                    backup.write(original.read())
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Erro ao guardar {STATE_FILE}: {e}")

# === Discord ===
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
last_stream_ids = {}
stream_lock = asyncio.Lock()

async def retry_get_json(session, url, retries=3, delay=2):
    for attempt in range(retries):
        try:
            async with session.get(url) as resp:
                return await resp.json()
        except Exception as e:
            log.warning(f"Tentativa {attempt+1} falhou: {e}")
            await asyncio.sleep(delay)
    raise Exception(f"Todas as tentativas falharam para: {url}")

async def check_youtube_live():
    await client.wait_until_ready()
    global last_stream_ids
    last_stream_ids = load_stream_state()

    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            try:
                log.info("🔍 Iniciando ciclo de verificação por grupos...")
                for i in range(0, len(YOUTUBE_CHANNEL_IDS), GROUP_SIZE):
                    group_ids = YOUTUBE_CHANNEL_IDS[i:i+GROUP_SIZE]
                    current_live_streams = {}

                    for yt_channel_id in group_ids:
                        url_search = (
                            "https://www.googleapis.com/youtube/v3/search"
                            "?part=snippet"
                            f"&channelId={yt_channel_id}"
                            "&eventType=live"
                            "&type=video"
                            f"&key={YOUTUBE_API_KEY}"
                        )
                        try:
                            data_search = await retry_get_json(session, url_search)
                            if "error" in data_search:
                                if data_search["error"].get("reason") == "quotaExceeded":
                                    log.warning("⚠️ Quota excedida. A pausar 1 hora.")
                                    await asyncio.sleep(3600)
                                    continue
                                log.error(f"Erro da API (search.list): {data_search['error']}")
                                continue

                            for item in data_search.get("items", []):
                                stream_id = item["id"]["videoId"]
                                title = item["snippet"]["title"]
                                url_stream = f"https://www.youtube.com/watch?v={stream_id}"
                                channel_name = item["snippet"]["channelTitle"]

                                current_live_streams[stream_id] = True

                                async with stream_lock:
                                    stream_data = last_stream_ids.get(stream_id)
                                    now = time.time()
                                    should_notify = (
                                        not stream_data or
                                        now - stream_data["timestamp"] > RESEND_INTERVAL
                                    )

                                    if should_notify:
                                        last_stream_ids[stream_id] = {
                                            "id": stream_id,
                                            "timestamp": now,
                                            "title": title,
                                            "channel_name": channel_name
                                        }
                                        save_stream_state(last_stream_ids)

                                        msg = (
                                            f"🔴 **{channel_name}** está em direto agora!\n"
                                            f"Título: **{title}**\n"
                                            f"🔗 {url_stream}\n"
                                            f"Canal: https://www.youtube.com/channel/{yt_channel_id}"
                                        )
                                        for guild in client.guilds:
                                            for channel in guild.text_channels:
                                                if channel.name.lower() == "race_notify":
                                                    try:
                                                        await channel.send(msg)
                                                        log.info(f"🔔 Notificado {guild.name} #{channel.name}")
                                                    except Exception as e:
                                                        log.error(f"Erro ao notificar {channel.name}: {e}")
                        except Exception as e:
                            log.error(f"Erro de conexão ao verificar {yt_channel_id}: {e}")

                    async with stream_lock:
                        to_remove = [sid for sid in last_stream_ids if sid not in current_live_streams]
                        for sid in to_remove:
                            last_stream_ids.pop(sid, None)
                        if to_remove:
                            save_stream_state(last_stream_ids)

                    log.info(f"🕒 Aguardando {GROUP_DELAY} segundos antes do próximo grupo...")
                    await asyncio.sleep(GROUP_DELAY)

                log.info(f"⏳ Aguardar {CHECK_INTERVAL_MINUTES} minutos até reiniciar ciclo completo...")
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                log.error(f"Erro no ciclo principal: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

@client.event
async def on_ready():
    log.info(f"Bot ligado como {client.user}")
    asyncio.create_task(check_youtube_live())

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    content = message.content.lower().strip()
    try:
        if content.startswith("!help"):
            help_msg = (
                "**Comandos disponíveis:**\n"
                "`!testelive` - Testa a notificação de live para o primeiro canal.\n"
                "`!resetnotificacao` - Reseta o estado das notificações para reenviar.\n"
                "`!estado` - Mostra as lives atuais notificadas.\n"
                "`!contribuir` - Mostra o email onde podes contribuir para a causa financeira do bot.\n"
                "`!help` - Mostras esta mensagem de ajuda.\n"
            )
            await message.channel.send(help_msg)

        if content.startswith("!contribuir"):
            contribuir_msg = (
                "🙏 Obrigado pelo interesse em contribuir com o bot!\n"
                "Podes ajudar de várias formas:\n"
                "- Enviando sugestões ou reportando bugs.\n"
                "- Contribuindo financeiramente através do pagamento por PayPal, tem em conta que os donativos são feitos de livre e espontanea vontade e não existe possiblidade de pedir o dinheiro de volta (REFUND).\n"
            )
            await message.channel.send(contribuir_msg, view=ContribuirView())

        elif content.startswith("!testelive"):
            if not YOUTUBE_CHANNEL_IDS:
                await message.channel.send("⚠️ Nenhum canal definido.")
                return
            yt_channel_id = YOUTUBE_CHANNEL_IDS[0]
            msg = (
                "📡 **Teste de notificação!**\n"
                f"🔗 https://www.youtube.com/channel/{yt_channel_id}"
            )
            for guild in client.guilds:
                for channel in guild.text_channels:
                    if channel.name.lower() == "race_notify":
                        try:
                            await channel.send(msg)
                        except Exception as e:
                            log.error(f"Erro no teste em {channel.name}: {e}")
        elif content.startswith("!resetnotificacao"):
            async with stream_lock:
                last_stream_ids.clear()
                save_stream_state(last_stream_ids)
            await message.channel.send("🔁 Notificações resetadas.")
        elif content.startswith("!estado"):
            async with stream_lock:
                if not last_stream_ids:
                    await message.channel.send("📬 Nenhuma live neste momento.")
                    return
                lines = [
                    f"🔴 **{info.get('channel_name', 'Desconhecido')}** - **{info['title']}**\nhttps://www.youtube.com/watch?v={info['id']}"
                    for info in last_stream_ids.values()
                ]
            await message.channel.send("**Lives atuais:**\n\n" + "\n\n".join(lines))
    except Exception as e:
        log.error(f"Erro no comando: {e}")

client.run(DISCORD_TOKEN)