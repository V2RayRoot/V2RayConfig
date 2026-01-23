import os
import re
import json
import logging
import random
import base64
import asyncio
import aiohttp
from datetime import datetime, timedelta
from telethon.sync import TelegramClient
from telethon.tl.types import Message, MessageEntityTextUrl, MessageEntityUrl, DocumentAttributeFilename
from telethon.sessions import StringSession
from telethon.errors import ChannelInvalidError, PeerIdInvalidError
from collections import defaultdict

# ======================== تنظیمات اولیه ========================
SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", None)
API_ID = os.getenv("TELEGRAM_API_ID", None)
API_HASH = os.getenv("TELEGRAM_API_HASH", None)
CHANNELS_FILE = "telegram_channels.json"
LOG_DIR = "Logs"
OUTPUT_DIR = "Configs"
NVPT_DIR = os.path.join(OUTPUT_DIR, "NVPT")
INVALID_CHANNELS_FILE = os.path.join(LOG_DIR, "invalid_channels.txt")
STATS_FILE = os.path.join(LOG_DIR, "channel_stats.json")
DESTINATION_CHANNEL = "@V2RayRootFree"

CONFIG_PATTERNS = {
    "vless": r"vless://[^\s\n]+",
    "vmess": r"vmess://[^\s\n]+",
    "shadowsocks": r"ss://[^\s\n]+",
    "trojan": r"trojan://[^\s\n]+",
    "mtproto": r"https://t\.me/proxy\?[^\s\n]+"
}

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

for path in [LOG_DIR, OUTPUT_DIR, NVPT_DIR]:
    if not os.path.exists(path):
        os.makedirs(path)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.handlers = []
file_handler = logging.FileHandler(os.path.join(LOG_DIR, "collector.log"), mode='w', encoding='utf-8')
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

def load_channels():
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        channels = json.load(f)
    logger.info(f"Loaded {len(channels)} channels from {CHANNELS_FILE}")
    return channels

def update_channels(channels):
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=4)
    logger.info(f"Updated {CHANNELS_FILE} with {len(channels)} channels")

def detect_operator(text):
    text_lower = text.lower()
    for keyword, op in OPERATORS.items():
        if keyword.lower() in text_lower:
            return op
    return None

def parse_channel_identifier(channel_str):
    channel_str = channel_str.strip()
    if channel_str.startswith('-100'):
        return int(channel_str)
    if channel_str.startswith('/c/'):
        try:
            return -100 * (10**9) + int(channel_str.replace('/c/', ''))
        except ValueError:
            return channel_str
    if channel_str.isdigit():
        return int(channel_str)
    return channel_str

def format_proxies_in_rows(proxies, per_row=4):
    lines = []
    for i in range(0, len(proxies), per_row):
        chunk = proxies[i:i+per_row]
        line = " | ".join([f"[Proxy {i+j+1}]({proxy})" for j, proxy in enumerate(chunk)])
        lines.append(line)
    return "\n".join(lines)

async def fetch_configs_and_proxies_from_channel(client, channel):
    configs = {"vless": [], "vmess": [], "shadowsocks": [], "trojan": [], "mtproto": []}
    operator_configs = defaultdict(list)
    proxies = []
    nvpt_files = []
    try:
        await client.get_entity(channel)
    except (ChannelInvalidError, PeerIdInvalidError, ValueError) as e:
        logger.error(f"Channel {channel} inaccessible: {str(e)}")
        return configs, operator_configs, proxies, nvpt_files, False

    try:
        today = datetime.now().date()
        min_proxy_date = today - timedelta(days=7)
        async for message in client.iter_messages(channel, limit=500):
            if not message.message and not getattr(message, 'media', None):
                continue
            text = message.message or ""
            operator = detect_operator(text)

            for proto, pattern in CONFIG_PATTERNS.items():
                matches = re.findall(pattern, text)
                if matches:
                    configs[proto].extend(matches)
                    if operator:
                        operator_configs[operator].extend(matches)

            if getattr(message, 'media', None):
                if getattr(message.media, 'document', None):
                    doc = message.media.document
                    if any(attr for attr in doc.attributes if isinstance(attr, DocumentAttributeFilename) and attr.file_name.lower().endswith(".nvpt")):
                        file_name = [attr.file_name for attr in doc.attributes if isinstance(attr, DocumentAttributeFilename)][0]
                        nvpt_path = os.path.join(NVPT_DIR, file_name)
                        if not os.path.exists(nvpt_path):
                            try:
                                await client.download_media(message, file=nvpt_path)
                                logger.info(f"Downloaded NVPT: {file_name} from {channel}")
                                nvpt_files.append({"file": nvpt_path, "source": channel})
                            except Exception as e:
                                logger.error(f"Failed to download NVPT {file_name} from {channel}: {str(e)}")

            if message.date.date() >= min_proxy_date:
                for proto in ["mtproto"]:
                    matches = re.findall(CONFIG_PATTERNS[proto], text)
                    if matches:
                        proxies.extend(matches)
                        if operator:
                            operator_configs[operator].extend(matches)

        return configs, operator_configs, proxies, nvpt_files, True
    except Exception as e:
        logger.error(f"Error fetching {channel}: {str(e)}")
        return configs, operator_configs, proxies, nvpt_files, False

def save_configs(configs, protocol):
    output_file = os.path.join(OUTPUT_DIR, f"{protocol}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        if configs:
            for config in configs:
                f.write(config + "\n")
        else:
            f.write("No configs found for this protocol.\n")
    logger.info(f"Saved {len(configs)} {protocol} configs")

def save_operator_configs(operator_configs):
    for op, configs in operator_configs.items():
        file_path = os.path.join(OUTPUT_DIR, f"{op}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            if configs:
                for config in configs:
                    f.write(config + "\n")
            else:
                f.write(f"No configs found for {op}.\n")
        logger.info(f"Saved {len(configs)} configs for operator {op}")

def save_nvpt_files(nvpt_files):
    logger.info(f"Total NVPT files downloaded: {len(nvpt_files)}")

async def send_message_to_destination(client, destination, message, parse_mode="markdown"):
    try:
        dest_identifier = parse_channel_identifier(destination)
        await client.send_message(dest_identifier, message, parse_mode=parse_mode)
        logger.info(f"Message sent to {destination}")
        print(f"✅ Message posted to {destination}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {destination}: {str(e)}")
        print(f"❌ Failed to send message to {destination}: {str(e)}")
        return False

async def send_file_to_destination(client, destination, file_path, caption=None):
    try:
        dest_identifier = parse_channel_identifier(destination)
        await client.send_file(dest_identifier, file_path, caption=caption)
        logger.info(f"File {file_path} sent to {destination}")
        print(f"✅ File posted to {destination}")
        return True
    except Exception as e:
        logger.error(f"Failed to send file {file_path} to {destination}: {str(e)}")
        print(f"❌ Failed to send file {file_path} to {destination}: {str(e)}")
        return False

async def post_configs_to_channel(client, all_configs, all_proxies, nvpt_files, channel_stats):
    if not channel_stats:
        logger.warning("No channel stats available.")
        return

    best_channel = max(channel_stats.items(), key=lambda x: x[1].get("score", 0))[0]

    for protocol, configs in all_configs.items():
        for idx, config in enumerate(configs, start=1):
            operator_tag = ""
            for op, op_configs in channel_stats.get(best_channel, {}).get("operator_configs", {}).items():
                if config in op_configs:
                    operator_tag = f" | {op}"
            message = f"⚙️🌐 {protocol.capitalize()} Config\n\n```{config}```\n\n🆔 Source: {best_channel}{operator_tag}"
            await send_message_to_destination(client, DESTINATION_CHANNEL, message)
            await asyncio.sleep(3)

    for idx, proxy in enumerate(all_proxies, start=1):
        message = f"🌐 Proxy {idx}\n{proxy}\n\n🆔 Source: {best_channel}"
        await send_message_to_destination(client, DESTINATION_CHANNEL, message)
        await asyncio.sleep(2)

    for idx, nvpt in enumerate(nvpt_files, start=1):
        file_path = nvpt["file"]
        source_channel = nvpt["source"]
        caption = f"📁 NVPT File ({idx}/{len(nvpt_files)})\n🆔 Source: {source_channel}"
        await send_file_to_destination(client, DESTINATION_CHANNEL, file_path, caption=caption)
        await asyncio.sleep(5)

def save_proxies(proxies):
    output_file = os.path.join(OUTPUT_DIR, "proxies.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        if proxies:
            for proxy in proxies:
                f.write(f"{proxy}\n")
        else:
            f.write("No proxies found.\n")
    logger.info(f"Saved {len(proxies)} proxies")

def save_invalid_channels(invalid_channels):
    with open(INVALID_CHANNELS_FILE, "w", encoding="utf-8") as f:
        if invalid_channels:
            for channel in invalid_channels:
                f.write(f"{channel}\n")
        else:
            f.write("No invalid channels.\n")
    logger.info(f"Saved {len(invalid_channels)} invalid channels")

def save_channel_stats(stats):
    stats_list = [{"channel": channel, **data} for channel, data in stats.items()]
    sorted_stats = sorted(stats_list, key=lambda x: x.get("score", 0), reverse=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_stats, f, ensure_ascii=False, indent=4)
    logger.info(f"Saved channel stats")

async def main():
    logger.info("Starting NVPT & Config collector...")
    print("🚀 Starting NVPT & Config collector...\n")

    if not SESSION_STRING or not API_ID or not API_HASH:
        print("Please set TELEGRAM_SESSION_STRING, TELEGRAM_API_ID, TELEGRAM_API_HASH in environment variables.")
        return

    try:
        api_id = int(API_ID)
    except ValueError:
        print("Invalid API ID format.")
        return

    TELEGRAM_CHANNELS = load_channels()
    session = StringSession(SESSION_STRING)

    try:
        async with TelegramClient(session, api_id, API_HASH) as client:
            if not await client.is_user_authorized():
                print("Invalid session string.")
                return

            all_configs = {"vless": [], "vmess": [], "shadowsocks": [], "trojan": [], "mtproto": []}
            all_operator_configs = defaultdict(list)
            all_proxies = []
            all_nvpt_files = []
            invalid_channels = []
            channel_stats = {}

            for channel in TELEGRAM_CHANNELS:
                print(f"\n📡 Fetching from {channel}...")
                configs, op_configs, proxies, nvpt_files, is_valid = await fetch_configs_and_proxies_from_channel(client, channel)
                if not is_valid:
                    invalid_channels.append(channel)
                    channel_stats[channel] = {"score": 0, "operator_configs": {}}
                    continue

                for proto in all_configs:
                    all_configs[proto].extend(configs.get(proto, []))
                for op in op_configs:
                    all_operator_configs[op].extend(op_configs[op])
                all_proxies.extend(proxies)
                all_nvpt_files.extend(nvpt_files)

                total_configs = sum(len(configs[p]) for p in configs)
                total_proxies = len(proxies)
                score = total_configs + total_proxies
                channel_stats[channel] = {"score": score, "operator_configs": op_configs}

            for proto in all_configs:
                all_configs[proto] = list(set(all_configs[proto]))
            all_proxies = list(set(all_proxies))
            for op in all_operator_configs:
                all_operator_configs[op] = list(set(all_operator_configs[op]))

            for proto in all_configs:
                save_configs(all_configs[proto], proto)
            save_operator_configs(all_operator_configs)
            save_proxies(all_proxies)
            save_invalid_channels(invalid_channels)
            save_channel_stats(channel_stats)

            await post_configs_to_channel(client, all_configs, all_proxies, all_nvpt_files, channel_stats)

            valid_channels = [c for c in TELEGRAM_CHANNELS if c not in invalid_channels]
            update_channels(valid_channels)

    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        print(f"Error: {str(e)}")
        return

    print("✅ Collection & posting process completed!")
    logger.info("Collection & posting process completed!")

if __name__ == "__main__":
    asyncio.run(main())
