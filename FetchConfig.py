import os
import re
import json
import logging
import random
import base64
import asyncio
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple

from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    Message,
    MessageEntityTextUrl,
    MessageEntityUrl
)
from telethon.errors import (
    ChannelInvalidError,
    PeerIdInvalidError,
    FloodWaitError
)

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

# ============================================================
# PATHS & FILES
# ============================================================

BASE_DIR = os.getcwd()

LOG_DIR = os.path.join(BASE_DIR, "Logs")
OUTPUT_DIR = os.path.join(BASE_DIR, "Config")
NVPT_DIR = os.path.join(OUTPUT_DIR, "nvpt")

CHANNELS_FILE = "telegram_channels.json"
INVALID_CHANNELS_FILE = os.path.join(LOG_DIR, "invalid_channels.txt")
STATS_FILE = os.path.join(LOG_DIR, "channel_stats.json")

DESTINATION_CHANNEL = "@V2RayRootFree"

# ============================================================
# CONSTANTS
# ============================================================

CONFIG_PATTERNS = {
    "vless": r"vless://[^\s\n]+",
    "vmess": r"vmess://[^\s\n]+",
    "shadowsocks": r"ss://[^\s\n]+",
    "trojan": r"trojan://[^\s\n]+",
}

PROXY_PATTERN = r"https:\/\/t\.me\/proxy\?server=[^&\s\)]+&port=\d+&secret=[^\s\)]+"

NVPT_EXTENSIONS = (".nvpt", ".npvt")
MAX_MESSAGE_SCAN = 500
NVPT_SCAN_DAYS = 7

# ============================================================
# OPERATORS
# ============================================================

OPERATORS = {
    "همراه اول": "HamrahAval",
    "#همراه_اول": "HamrahAval",
    "ایرانسل": "Irancell",
    "#ایرانسل": "Irancell",
    "مخابرات": "Makhaberat",
    "#مخابرات": "Makhaberat",
    "سامانتل": "Samantel",
    "#سامانتل": "Samantel",
    "سامان تل": "Samantel",
    "#سامان_تل": "Samantel",
    "شاتل": "Shatel",
    "#شاتل": "Shatel",
}

# ============================================================
# DIRECTORY INIT
# ============================================================

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(NVPT_DIR, exist_ok=True)

# ============================================================
# LOGGING SETUP
# ============================================================

logger = logging.getLogger("collector")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()

file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "collector.log"),
    mode="w",
    encoding="utf-8"
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
)
file_handler.setLevel(logging.DEBUG)

logger.addHandler(file_handler)

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def load_channels() -> List[str]:
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        channels = json.load(f)
    logger.info(f"Loaded {len(channels)} channels")
    return channels


def update_channels(channels: List[str]) -> None:
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=4)
    logger.info(f"Updated channel list ({len(channels)})")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_operator(text: str) -> str | None:
    text = text.lower()
    for key, op in OPERATORS.items():
        if key.lower() in text:
            return op
    return None


def extract_proxies_from_message(message: Message) -> List[str]:
    proxies = []
    text = message.message or ""

    proxies.extend(re.findall(PROXY_PATTERN, text))

    if message.entities:
        for ent in message.entities:
            if isinstance(ent, (MessageEntityTextUrl, MessageEntityUrl)):
                url = getattr(ent, "url", None)
                if not url:
                    url = text[ent.offset : ent.offset + ent.length]
                if url.startswith("https://t.me/proxy?"):
                    proxies.append(url)

    return proxies


def extract_configs(text: str) -> Dict[str, List[str]]:
    found = {k: [] for k in CONFIG_PATTERNS}
    for proto, pattern in CONFIG_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            found[proto].extend(matches)
    return found


# ============================================================
# NVPT SCANNER
# ============================================================

async def scan_nvpt_files(
    client: TelegramClient,
    channel: str
) -> List[Dict]:
    """
    Scan channel messages for .nvpt/.npvt files
    """
    results = []
    min_date = datetime.now().date() - timedelta(days=NVPT_SCAN_DAYS)

    async for msg in client.iter_messages(channel, limit=MAX_MESSAGE_SCAN):
        if not msg.date or msg.date.date() < min_date:
            break

        if msg.file and msg.file.name:
            name = msg.file.name.lower()
            if name.endswith(NVPT_EXTENSIONS):
                try:
                    save_path = os.path.join(NVPT_DIR, msg.file.name)
                    downloaded = await msg.download_media(file=save_path)

                    file_hash = sha256_file(downloaded)

                    results.append({
                        "path": downloaded,
                        "hash": file_hash,
                        "channel": channel,
                        "message_id": msg.id
                    })

                    logger.info(f"[NVPT] {channel} -> {msg.file.name}")

                except Exception as e:
                    logger.error(f"NVPT download failed {channel}: {e}")

    return results


# ============================================================
# CHANNEL COLLECTOR
# ============================================================

async def fetch_from_channel(
    client: TelegramClient,
    channel: str
) -> Tuple[dict, dict, list, list, bool]:

    configs = {k: [] for k in CONFIG_PATTERNS}
    operator_configs = defaultdict(list)
    proxies = []
    nvpt_files = []

    try:
        await client.get_entity(channel)
    except (ChannelInvalidError, PeerIdInvalidError, ValueError):
        logger.error(f"Invalid channel: {channel}")
        return configs, operator_configs, proxies, nvpt_files, False

    today = datetime.now().date()
    min_proxy_date = today - timedelta(days=7)

    async for msg in client.iter_messages(channel, limit=MAX_MESSAGE_SCAN):
        if not msg.date:
            continue

        if msg.message:
            extracted = extract_configs(msg.message)
            operator = detect_operator(msg.message)

            for proto, items in extracted.items():
                if items:
                    configs[proto].extend(items)
                    if operator:
                        operator_configs[operator].extend(items)

        if msg.date.date() >= min_proxy_date:
            proxies.extend(extract_proxies_from_message(msg))

    nvpt_files = await scan_nvpt_files(client, channel)

    logger.info(
        f"[{channel}] "
        f"configs={sum(len(v) for v in configs.values())} "
        f"proxies={len(proxies)} "
        f"nvpt={len(nvpt_files)}"
    )

    return configs, operator_configs, proxies, nvpt_files, True


# ============================================================
# STATS HANDLING
# ============================================================

def build_channel_stats(
    channel: str,
    configs: dict,
    proxies: list,
    nvpt_files: list,
    error: str | None = None
) -> dict:
    total_configs = sum(len(v) for v in configs.values())
    score = total_configs + len(proxies) + (len(nvpt_files) * 2)

    return {
        "channel": channel,
        "vless": len(configs["vless"]),
        "vmess": len(configs["vmess"]),
        "shadowsocks": len(configs["shadowsocks"]),
        "trojan": len(configs["trojan"]),
        "proxies": len(proxies),
        "nvpt_files": len(nvpt_files),
        "total_configs": total_configs,
        "score": score,
        "error": error
    }


def save_stats(stats: Dict[str, dict]) -> None:
    sorted_stats = sorted(
        stats.values(),
        key=lambda x: x["score"],
        reverse=True
    )
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_stats, f, ensure_ascii=False, indent=4)
    logger.info("Channel stats saved")

# ============================================================
#  Poster / Main Loop / NVPT Posting / Rate Limit
# ============================================================

def format_proxies(proxies: list, per_row: int = 4) -> str:
    lines = []
    for i in range(0, len(proxies), per_row):
        chunk = proxies[i:i + per_row]
        line = " | ".join([f"[Proxy {i+j+1}]({p})" for j, p in enumerate(chunk)])
        lines.append(line)
    return "\n".join(lines)


def parse_channel_id(channel_str: str) -> str | int:
    channel_str = channel_str.strip()
    if channel_str.startswith("-100") or channel_str.isdigit():
        return int(channel_str)
    if channel_str.startswith("/c/"):
        try:
            cid = int(channel_str.replace("/c/", ""))
            return -100 * (10**9) + cid
        except ValueError:
            return channel_str
    return channel_str


async def send_message(
    client: TelegramClient,
    destination: str,
    message: str,
    parse_mode: str = "markdown"
) -> bool:
    try:
        dest_id = parse_channel_id(destination)
        await client.send_message(dest_id, message, parse_mode=parse_mode)
        logger.info(f"Sent message to {destination}")
        print(f"✅ Posted message to {destination}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {destination}: {e}")
        print(f"❌ Failed to post message to {destination}")
        return False


async def post_configs_and_nvpt(
    client: TelegramClient,
    all_configs: dict,
    all_proxies: list,
    all_nvpt: list,
    channel_stats: dict
):
    if not channel_stats:
        print("⚠️ No stats, cannot determine best channel")
        return

    # Determine best channel by score
    best_channel = max(channel_stats.items(), key=lambda x: x[1].get("score", 0))[0]

    # Aggregate channel configs & nvpt
    channel_configs, channel_proxies, channel_nvpt = [], [], []

    for proto, items in all_configs.items():
        channel_configs.extend(items)
    channel_proxies = all_proxies
    channel_nvpt = all_nvpt

    if not channel_configs and not channel_nvpt:
        print(f"⚠️ No configs/NVPT to post from {best_channel}")
        return

    POST_COUNT = 3  # 3 configs + 3 NVPT

    # Shuffle & pick configs
    random.shuffle(channel_configs)
    selected_configs = channel_configs[:POST_COUNT]

    random.shuffle(channel_nvpt)
    selected_nvpt = channel_nvpt[:POST_COUNT]

    # --- Post Configs ---
    for idx, cfg in enumerate(selected_configs, start=1):
        proto_type = "Config"
        message = f"⚙️🌐 {proto_type} ({idx}/{len(selected_configs)})\n\n```{cfg}```"

        # Add proxies
        if channel_proxies:
            random.shuffle(channel_proxies)
            proxies_formatted = format_proxies(channel_proxies[:8])
            message += "\n" + proxies_formatted

        # Add footer
        message += "\n\n🆔 @V2RayRootFree"

        await send_message(client, DESTINATION_CHANNEL, message)
        await asyncio.sleep(8)

    # --- Post NVPT Files ---
    for idx, nvpt in enumerate(selected_nvpt, start=1):
        file_path = nvpt.get("path")
        channel_source = nvpt.get("channel")
        msg_id = nvpt.get("message_id")
        message = f"📂 NVPT File ({idx}/{len(selected_nvpt)}) from [{channel_source}](https://t.me/c/{channel_source}/{msg_id})"
        try:
            await client.send_file(
                parse_channel_id(DESTINATION_CHANNEL),
                file_path,
                caption=message
            )
            logger.info(f"Posted NVPT {file_path}")
            print(f"📤 Posted NVPT {file_path}")
        except Exception as e:
            logger.error(f"Failed NVPT post: {file_path} -> {e}")
        await asyncio.sleep(8)


# ============================================================
# SAVE FUNCTIONS EXTENDED
# ============================================================

def save_nvpt_files(nvpt_list: list) -> None:
    for nvpt in nvpt_list:
        src_path = nvpt.get("path")
        dst_file = os.path.join(NVPT_DIR, os.path.basename(src_path))
        if os.path.exists(src_path):
            try:
                with open(src_path, "rb") as sf, open(dst_file, "wb") as df:
                    df.write(sf.read())
            except Exception as e:
                logger.error(f"Failed to save NVPT {src_path}: {e}")


# ============================================================
# MAIN ASYNC LOOP
# ============================================================

async def main():
    print("🚀 Starting Telegram Config & NVPT Collector\n")
    logger.info("Starting Collector Process")

    if not SESSION_STRING:
        print("⚠️ TELEGRAM_SESSION_STRING not set")
        return
    if not API_ID or not API_HASH:
        print("⚠️ TELEGRAM_API_ID / TELEGRAM_API_HASH not set")
        return

    try:
        api_id_int = int(API_ID)
    except ValueError:
        print("⚠️ Invalid API_ID")
        return

    channels = load_channels()
    invalid_channels = []
    stats = {}
    all_configs = {k: [] for k in CONFIG_PATTERNS}
    all_operator_configs = defaultdict(list)
    all_proxies = []
    all_nvpt = []

    session = StringSession(SESSION_STRING)
    try:
        async with TelegramClient(session, api_id_int, API_HASH) as client:
            if not await client.is_user_authorized():
                print("⚠️ Invalid session string")
                return

            for ch in channels:
                print(f"\n📡 Fetching from {ch}")
                try:
                    ch_configs, ch_op_cfg, ch_proxies, ch_nvpt, valid = await fetch_from_channel(client, ch)
                    if not valid:
                        invalid_channels.append(ch)
                        stats[ch] = build_channel_stats(ch_configs, [], [], [], "Invalid channel")
                        continue

                    # Merge all
                    for proto in all_configs:
                        all_configs[proto].extend(ch_configs[proto])
                    for op in ch_op_cfg:
                        all_operator_configs[op].extend(ch_op_cfg[op])
                    all_proxies.extend(ch_proxies)
                    all_nvpt.extend(ch_nvpt)

                    stats[ch] = build_channel_stats(ch, ch_configs, ch_proxies, ch_nvpt)

                except Exception as e:
                    logger.error(f"Error fetching {ch}: {e}")
                    invalid_channels.append(ch)
                    stats[ch] = build_channel_stats(ch, {}, [], [], str(e))

            # Deduplicate
            for proto in all_configs:
                all_configs[proto] = list(set(all_configs[proto]))
            for op in all_operator_configs:
                all_operator_configs[op] = list(set(all_operator_configs[op]))
            all_proxies = list(set(all_proxies))
            all_nvpt = list({nvpt["hash"]: nvpt for nvpt in all_nvpt}.values())

            # Save outputs
            for proto in all_configs:
                with open(os.path.join(OUTPUT_DIR, f"{proto}.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(all_configs[proto]) or f"No {proto} configs found\n")
            for op, cfg in all_operator_configs.items():
                with open(os.path.join(OUTPUT_DIR, f"{op}.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(cfg) or f"No configs for {op}\n")
            with open(os.path.join(OUTPUT_DIR, "proxies.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(all_proxies) or "No proxies found\n")
            with open(INVALID_CHANNELS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(invalid_channels) or "No invalid channels\n")
            save_nvpt_files(all_nvpt)
            save_stats(stats)

            # Post configs + nvpt to destination
            await post_configs_and_nvpt(client, all_configs, all_proxies, all_nvpt, stats)

            # Update valid channels
            valid_channels = [c for c in channels if c not in invalid_channels]
            update_channels(valid_channels)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"⚠️ Fatal error: {e}")

    print("\n✅ Collection process completed!")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
