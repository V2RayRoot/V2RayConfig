import os
import re
import json
import logging
import random
import base64
import asyncio
from datetime import datetime, timedelta
from telethon.sync import TelegramClient
from telethon.tl.types import Message, MessageEntityTextUrl, MessageEntityUrl
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.sessions import StringSession
from telethon.errors import ChannelInvalidError, PeerIdInvalidError
from collections import defaultdict

SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", None)
API_ID = os.getenv("TELEGRAM_API_ID", None)
API_HASH = os.getenv("TELEGRAM_API_HASH", None)
CHANNELS_FILE = "telegram_channels.json"
LOG_DIR = "Logs"
OUTPUT_DIR = "Config"
NPVT_DIR = os.path.join(OUTPUT_DIR, "npvt")
INVALID_CHANNELS_FILE = os.path.join(LOG_DIR, "invalid_channels.txt")
STATS_FILE = os.path.join(LOG_DIR, "channel_stats.json")
DESTINATION_CHANNEL = "@V2RayRootFree"
CONFIG_PATTERNS = {
    "vless": r"vless://[^\s\n]+",
    "vmess": r"vmess://[^\s\n]+",
    "shadowsocks": r"ss://[^\s\n]+",
    "trojan": r"trojan://[^\s\n]+"
}
PROXY_PATTERN = r"https:\/\/t\.me\/proxy\?server=[^&\s\)]+&port=\d+&secret=[^\s\)]+"

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

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

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

if not os.path.exists(OUTPUT_DIR):
    logger.info(f"Creating directory: {OUTPUT_DIR}")
    os.makedirs(OUTPUT_DIR)

if not os.path.exists(NPVT_DIR):
    logger.info(f"Creating directory: {NPVT_DIR}")
    os.makedirs(NPVT_DIR)

def extract_server_address(config, protocol):
    try:
        if protocol == "vmess":
            config_data = config.split("vmess://")[1]
            decoded = base64.b64decode(config_data).decode("utf-8")
            config_json = json.loads(decoded)
            return config_json.get("add", "")
        else:
            match = re.search(r"@([^\s:]+):", config)
            if match:
                return match.group(1)
            match = re.search(r"{}://[^\s@]+?([^\s:]+):".format(protocol), config)
            if match:
                return match.group(1)
        return None
    except Exception as e:
        logger.error(f"Failed to extract server address from {config}: {str(e)}")
        return None

def extract_proxies_from_message(message):
    proxies = []
    proxies += re.findall(PROXY_PATTERN, message.message or "")
    if hasattr(message, 'entities') and message.entities:
        text = message.message or ""
        for entity in message.entities:
            if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                if hasattr(entity, 'url'):
                    url = entity.url
                else:
                    offset = entity.offset
                    length = entity.length
                    url = text[offset:offset+length]
                if url.startswith("https://t.me/proxy?"):
                    proxies.append(url)
    return proxies

def detect_operator(text):
    text_lower = text.lower()
    for keyword, op in OPERATORS.items():
        if keyword.lower() in text_lower:
            return op
    return None

def extract_npvt_filename(message):
    file_name = None
    if getattr(message, "file", None):
        file_name = getattr(message.file, "name", None)

    if not file_name and getattr(message, "document", None):
        for attr in getattr(message.document, "attributes", []):
            if hasattr(attr, "file_name"):
                file_name = attr.file_name
                break

    if file_name and file_name.lower().endswith(".npvt"):
        return file_name
    return None

async def download_npvt_from_message(client, message, channel):
    file_name = extract_npvt_filename(message)
    if not file_name:
        return None

    safe_channel = re.sub(r"[^\\w\\-\\.]+", "_", str(channel))
    base_name = os.path.basename(file_name)
    output_name = f"{safe_channel}_{message.id}_{base_name}"
    output_path = os.path.join(NPVT_DIR, output_name)

    if os.path.exists(output_path):
        logger.info(f"[{channel}] NPVT already downloaded: {output_path}")
        return output_path

    try:
        downloaded_path = await client.download_media(message, file=output_path)
        if downloaded_path:
            logger.info(f"[{channel}] Downloaded NPVT file: {downloaded_path}")
            print(f"✅ [{channel}] Downloaded NPVT: {os.path.basename(downloaded_path)}")
            return downloaded_path
    except Exception as e:
        logger.error(f"[{channel}] Failed to download NPVT from message {message.id}: {str(e)}")

    return None

async def fetch_configs_and_proxies_from_channel(client, channel):
    configs = {"vless": [], "vmess": [], "shadowsocks": [], "trojan": []}
    config_timeline = []
    operator_configs = defaultdict(list)
    proxies = []
    proxy_timeline = []
    npvt_files = []
    try:
        channel_entity = await resolve_channel_target(client, channel)
    except (ChannelInvalidError, PeerIdInvalidError, ValueError) as e:
        logger.error(f"Channel {channel} does not exist or is inaccessible: {str(e)}")
        return configs, config_timeline, operator_configs, proxies, npvt_files, proxy_timeline, False
    except Exception as e:
        logger.error(f"Channel {channel} could not be resolved: {str(e)}")
        return configs, config_timeline, operator_configs, proxies, npvt_files, proxy_timeline, False

    try:
        message_count = 0
        configs_found_count = 0
        today = datetime.now().date()
        min_proxy_date = today - timedelta(days=7)

        async for message in client.iter_messages(channel_entity, limit=150):
            message_count += 1
            if message.date:
                message_date = message.date.date()
            else:
                continue

            downloaded_npvt = await download_npvt_from_message(client, message, channel)
            if downloaded_npvt:
                npvt_files.append({
                    "file_path": downloaded_npvt,
                    "source": str(channel)
                })

            if isinstance(message, Message) and message.message:
                text = message.message

                operator = detect_operator(text)

                for protocol, pattern in CONFIG_PATTERNS.items():
                    matches = re.findall(pattern, text)
                    if matches:
                        logger.info(f"[{channel}] Found {len(matches)} {protocol} configs in message {message.id}")
                        print(f"✅ [{channel}] Found {len(matches)} {protocol} configs")
                        configs[protocol].extend(matches)
                        for config in matches:
                            config_timeline.append({
                                "protocol": protocol.capitalize(),
                                "config": config,
                                "source": str(channel)
                            })
                        configs_found_count += len(matches)
                        if operator:
                            for config in matches:
                                operator_configs[operator].append(config)

                if message_date >= min_proxy_date:
                    proxy_links = extract_proxies_from_message(message)
                    if proxy_links:
                        logger.info(f"[{channel}] Found {len(proxy_links)} proxies in message {message.id}")
                        print(f"✅ [{channel}] Found {len(proxy_links)} proxies")
                        proxies.extend(proxy_links)
                        for proxy in proxy_links:
                            proxy_timeline.append({
                                "proxy": proxy,
                                "source": str(channel)
                            })
        
        summary = f"[{channel}] ✔️ Processed {message_count} messages → Found {configs_found_count} configs + {len(proxies)} proxies + {len(npvt_files)} npvt"
        logger.info(summary)
        print(summary)
        return configs, config_timeline, operator_configs, proxies, npvt_files, proxy_timeline, True
    except Exception as e:
        logger.error(f"Failed to fetch from {channel}: {str(e)}")
        print(f"❌ [{channel}] Error: {str(e)}")
        return configs, config_timeline, operator_configs, proxies, npvt_files, proxy_timeline, False

def save_configs(configs, protocol):
    output_file = os.path.join(OUTPUT_DIR, f"{protocol}.txt")
    logger.info(f"Saving configs to {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        if configs:
            for config in configs:
                f.write(config + "\n")
            logger.info(f"Saved {len(configs)} {protocol} configs to {output_file}")
        else:
            f.write("No configs found for this protocol.\n")
            logger.info(f"No {protocol} configs found, wrote placeholder to {output_file}")

def save_operator_configs(operator_configs):
    for op, configs in operator_configs.items():
        output_file = os.path.join(OUTPUT_DIR, f"{op}.txt")
        logger.info(f"Saving operator configs to {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            if configs:
                for config in configs:
                    f.write(config + "\n")
                logger.info(f"Saved {len(configs)} configs for {op} to {output_file}")
            else:
                f.write(f"No configs found for {op}.\n")
                logger.info(f"No configs found for {op}, wrote placeholder to {output_file}")

def save_proxies(proxies):
    output_file = os.path.join(OUTPUT_DIR, f"proxies.txt")
    logger.info(f"Saving proxies to {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        if proxies:
            for proxy in proxies:
                f.write(f"{proxy}\n")
            logger.info(f"Saved {len(proxies)} proxies to {output_file}")
        else:
            f.write("No proxies found.\n")
            logger.info("No proxies found, wrote placeholder to proxies.txt")

def save_invalid_channels(invalid_channels):
    logger.info(f"Saving invalid channels to {INVALID_CHANNELS_FILE}")
    with open(INVALID_CHANNELS_FILE, "w", encoding="utf-8") as f:
        if invalid_channels:
            for channel in invalid_channels:
                f.write(f"{channel}\n")
            logger.info(f"Saved {len(invalid_channels)} invalid channels to {INVALID_CHANNELS_FILE}")
        else:
            f.write("No invalid channels found.\n")
            logger.info(f"No invalid channels found, wrote placeholder to {INVALID_CHANNELS_FILE}")

def save_channel_stats(stats):
    logger.info(f"Saving channel stats to {STATS_FILE}")
    stats_list = [{"channel": channel, **data} for channel, data in stats.items()]
    sorted_stats = sorted(stats_list, key=lambda x: x["score"], reverse=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_stats, f, ensure_ascii=False, indent=4)
    logger.info(f"Saved channel stats to {STATS_FILE}")

def format_proxies_in_rows(proxies, per_row=4):
    lines = []
    for i in range(0, len(proxies), per_row):
        chunk = proxies[i:i+per_row]
        line = " | ".join([f"[Proxy {i+j+1}]({proxy})" for j, proxy in enumerate(chunk)])
        lines.append(line)
    return "\n".join(lines)

def format_proxies_for_caption(proxies, max_count=4):
    if not proxies:
        return "No proxies found"

    selected = list(proxies[:max_count])
    links = [f"[Proxy {i+1}]({item['proxy']})" for i, item in enumerate(selected)]
    first_row = " | ".join(links[:4])
    second_row = " | ".join(links[4:8])
    if second_row:
        return f"{first_row}\n{second_row}"
    return first_row

def build_sources_text(config_source, npvt_source, proxy_sources):
    proxies_sources_text = ", ".join([format_channel_source(src) for src in proxy_sources]) if proxy_sources else "N/A"
    return (
        f"- Config: {format_channel_source(config_source)}\n"
        f"- NPVT: {format_channel_source(npvt_source)}\n"
        f"- Proxies: {proxies_sources_text}"
    )

def format_channel_source(channel):
    if not isinstance(channel, str):
        return str(channel)

    value = channel.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"
    if value.startswith("+"):
        return f"https://t.me/{value}"
    if value.startswith("joinchat/"):
        return f"https://t.me/{value}"
    if value.startswith("t.me/"):
        return f"https://{value}"
    return value

def build_npvt_caption(proxies_text, index, total, config_source, npvt_source, proxy_sources, config_type, config_value):
    sources_text = build_sources_text(config_source, npvt_source, proxy_sources)
    return (
        f"🧩 **NPVT + Config Pack** ({index}/{total})\n\n"
        f"⚙️ **Random {config_type} Config**\n"
        f"```{config_value}```\n\n"
        f"🔗 **Latest 8 Proxies**\n{proxies_text}\n\n"
        f"📡 **Source Channels**\n{sources_text}\n\n"
        f"🆔 @V2RayRootFree"
    )

def select_post_payloads(last_channels, channel_recent_configs, channel_recent_npvt, best_channel, required_count):
    selected = []
    used_config_idx = defaultdict(int)
    used_npvt_idx = defaultdict(int)

    def take_one_from_channel(channel):
        configs = channel_recent_configs.get(channel, [])
        npvts = channel_recent_npvt.get(channel, [])
        config_idx = used_config_idx.get(channel, 0)
        npvt_idx = used_npvt_idx.get(channel, 0)

        if config_idx < len(configs) and npvt_idx < len(npvts):
            payload = {
                "channel": channel,
                "config_item": configs[config_idx],
                "npvt_item": npvts[npvt_idx]
            }
            used_config_idx[channel] = config_idx + 1
            used_npvt_idx[channel] = npvt_idx + 1
            return payload
        return None

    for channel in last_channels:
        payload = take_one_from_channel(channel)
        if payload:
            selected.append(payload)
        if len(selected) == required_count:
            return selected

    if best_channel:
        while len(selected) < required_count:
            payload = take_one_from_channel(best_channel)
            if not payload:
                break
            selected.append(payload)

    if len(selected) < required_count:
        for channel in last_channels:
            while len(selected) < required_count:
                payload = take_one_from_channel(channel)
                if not payload:
                    break
                selected.append(payload)
            if len(selected) == required_count:
                break

    if selected and len(selected) < required_count:
        source = list(selected)
        repeat_idx = 0
        while len(selected) < required_count:
            selected.append(source[repeat_idx % len(source)])
            repeat_idx += 1

    return selected[:required_count]

def select_proxy_items_for_post(random_channels, channel_recent_proxies, best_channel, required_count=8):
    selected = []

    for channel in random_channels:
        selected.extend(channel_recent_proxies.get(channel, []))
        if len(selected) >= required_count:
            break

    if len(selected) < required_count and best_channel:
        selected.extend(channel_recent_proxies.get(best_channel, []))

    return selected[:required_count]

def get_best_scoring_channel(channel_stats, channels):
    best_channel = None
    best_score = -1
    for channel in channels:
        score = channel_stats.get(channel, {}).get("score", 0)
        if score > best_score:
            best_score = score
            best_channel = channel
    return best_channel

def select_last_items_with_fallback(last_channels, items_by_channel, best_channel, required_count):
    selected = []
    used_index = defaultdict(int)

    for channel in last_channels:
        channel_items = items_by_channel.get(channel, [])
        if channel_items:
            selected.append(channel_items[0])
            used_index[channel] = 1
        if len(selected) == required_count:
            return selected

    if best_channel:
        best_items = items_by_channel.get(best_channel, [])
        idx = used_index.get(best_channel, 0)
        while idx < len(best_items) and len(selected) < required_count:
            selected.append(best_items[idx])
            idx += 1
        used_index[best_channel] = idx

    if len(selected) < required_count:
        for channel in last_channels:
            channel_items = items_by_channel.get(channel, [])
            idx = used_index.get(channel, 0)
            while idx < len(channel_items) and len(selected) < required_count:
                selected.append(channel_items[idx])
                idx += 1
            used_index[channel] = idx

    if selected and len(selected) < required_count:
        source = list(selected)
        repeat_idx = 0
        while len(selected) < required_count:
            selected.append(source[repeat_idx % len(source)])
            repeat_idx += 1

    return selected[:required_count]

def parse_channel_identifier(channel_str):
    if not isinstance(channel_str, str):
        return channel_str

    channel_str = channel_str.strip()

    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if channel_str.startswith(prefix):
            channel_str = channel_str[len(prefix):]
            break

    if "/" in channel_str and not channel_str.startswith(("c/", "joinchat/")):
        channel_str = channel_str.split("/", 1)[0]

    if channel_str.startswith("+") or channel_str.startswith("joinchat/"):
        return channel_str
    
    if channel_str.startswith('-100'):
        return int(channel_str)
    
    if channel_str.startswith('/c/') or channel_str.startswith('c/'):
        try:
            channel_id = int(channel_str.replace('/c/', '').replace('c/', ''))
            return -100 * (10**9) + channel_id
        except ValueError:
            return channel_str
    
    if channel_str.isdigit():
        return int(channel_str)

    if channel_str and not channel_str.startswith('@'):
        return f"@{channel_str}"
    
    return channel_str

def extract_invite_hash(channel):
    if not isinstance(channel, str):
        return None

    value = channel.strip()

    if value.startswith("https://t.me/+"):
        return value.split("https://t.me/+", 1)[1].split("/", 1)[0]
    if value.startswith("http://t.me/+"):
        return value.split("http://t.me/+", 1)[1].split("/", 1)[0]
    if value.startswith("t.me/+"):
        return value.split("t.me/+", 1)[1].split("/", 1)[0]
    if value.startswith("+"):
        return value[1:].split("/", 1)[0]

    if value.startswith("https://t.me/joinchat/"):
        return value.split("https://t.me/joinchat/", 1)[1].split("/", 1)[0]
    if value.startswith("http://t.me/joinchat/"):
        return value.split("http://t.me/joinchat/", 1)[1].split("/", 1)[0]
    if value.startswith("t.me/joinchat/"):
        return value.split("t.me/joinchat/", 1)[1].split("/", 1)[0]
    if value.startswith("joinchat/"):
        return value.split("joinchat/", 1)[1].split("/", 1)[0]

    return None

async def resolve_channel_target(client, channel):
    invite_hash = extract_invite_hash(channel)
    if invite_hash:
        try:
            import_result = await client(ImportChatInviteRequest(invite_hash))
            chats = getattr(import_result, "chats", None)
            if chats:
                return chats[0]
        except Exception as e:
            logger.info(f"Invite import skipped/failed for {channel}: {str(e)}")

        try:
            invite_info = await client(CheckChatInviteRequest(invite_hash))
            if hasattr(invite_info, "chat") and invite_info.chat:
                return invite_info.chat
        except Exception as e:
            logger.error(f"Failed to resolve private invite {channel}: {str(e)}")
            raise

        raise ValueError(f"Cannot resolve private invite link: {channel}")

    parsed = parse_channel_identifier(channel)
    return await client.get_entity(parsed)

async def send_message_to_destination(client, destination, message, parse_mode="markdown", reply_to=None):
    try:
        if isinstance(destination, str):
            dest_identifier = await resolve_channel_target(client, destination)
        else:
            dest_identifier = destination
        
        await client.send_message(dest_identifier, message, parse_mode=parse_mode, reply_to=reply_to)
        logger.info(f"Successfully sent message to {destination}")
        print(f"✅ Message posted to {destination}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {destination}: {str(e)}")
        print(f"❌ Failed to send message to {destination}: {str(e)}")
        return False

async def send_file_to_destination(client, destination, file_path, caption, parse_mode="markdown"):
    try:
        if isinstance(destination, str):
            dest_identifier = await resolve_channel_target(client, destination)
        else:
            dest_identifier = destination

        sent_message = await client.send_file(dest_identifier, file_path, caption=caption, parse_mode=parse_mode)
        logger.info(f"Successfully sent file to {destination}: {file_path}")
        print(f"✅ File posted to {destination}: {os.path.basename(file_path)}")
        return sent_message
    except Exception as e:
        logger.error(f"Failed to send file to {destination}: {str(e)}")
        print(f"❌ Failed to send file to {destination}: {str(e)}")
        return None

async def post_config_and_proxies_to_channel(client, channel_stats, valid_channels, channel_recent_configs, channel_recent_npvt, channel_recent_proxies):
    POST_COUNT = 5

    if not valid_channels:
        logger.warning("No valid channels available for post selection.")
        print("⚠️  No valid channels available")
        return

    random_channels = random.sample(valid_channels, min(POST_COUNT, len(valid_channels)))
    best_channel = get_best_scoring_channel(channel_stats, valid_channels)

    selected_payloads = select_post_payloads(
        random_channels,
        channel_recent_configs,
        channel_recent_npvt,
        best_channel,
        POST_COUNT
    )

    random.shuffle(selected_payloads)

    if not selected_payloads:
        logger.warning("No payloads available to post.")
        print("⚠️  No payloads available to post")
        return

    selected_proxy_items = select_proxy_items_for_post(
        random_channels,
        channel_recent_proxies,
        best_channel,
        required_count=8
    )

    if not selected_proxy_items:
        logger.warning("No proxy items available to post.")
        print("⚠️  No proxy items available to post")
        return

    proxy_sources = list(dict.fromkeys([item["source"] for item in selected_proxy_items]))

    try:
        destination_entity = await resolve_channel_target(client, DESTINATION_CHANNEL)
    except Exception as e:
        logger.error(f"Failed to resolve destination channel {DESTINATION_CHANNEL}: {str(e)}")
        print(f"❌ Failed to resolve destination channel: {str(e)}")
        return

    for i, payload in enumerate(selected_payloads, start=1):
        source_channel = payload["channel"]
        config_item = payload["config_item"]
        npvt_item = payload["npvt_item"]

        config_type = config_item["protocol"]
        selected_config = config_item["config"]
        config_source = config_item["source"]
        npvt_file = npvt_item["file_path"]
        npvt_source = npvt_item["source"]

        proxies_text = format_proxies_for_caption(selected_proxy_items, max_count=8)
        caption = build_npvt_caption(
            proxies_text,
            i,
            POST_COUNT,
            config_source,
            npvt_source,
            proxy_sources,
            config_type,
            selected_config
        )

        sent_file_message = await send_file_to_destination(
            client,
            destination_entity,
            npvt_file,
            caption,
            parse_mode="markdown"
        )

        success = bool(sent_file_message)
        if success:
            logger.info(f"Posted {config_type} + NPVT ({i}/{POST_COUNT})")
            print(f"📤 Posted NPVT + config {i}/{POST_COUNT}")
        else:
            logger.error(f"Failed to post NPVT + config ({i}/{POST_COUNT})")

        await asyncio.sleep(4)


async def main():
    logger.info("Starting config+proxy collection process")
    print("🚀 Starting config+proxy collection process...\n")
    invalid_channels = []
    channel_stats = {}

    if not SESSION_STRING:
        logger.error("No session string provided.")
        print("Please set TELEGRAM_SESSION_STRING in environment variables.")
        return
    if not API_ID or not API_HASH:
        logger.error("API ID or API Hash not provided.")
        print("Please set TELEGRAM_API_ID and TELEGRAM_API_HASH in environment variables.")
        return

    try:
        api_id = int(API_ID)
    except ValueError:
        logger.error("Invalid TELEGRAM_API_ID format. It must be a number.")
        print("Invalid TELEGRAM_API_ID format. It must be a number.")
        return

    TELEGRAM_CHANNELS = load_channels()
    session = StringSession(SESSION_STRING)

    try:
        async with TelegramClient(session, api_id, API_HASH) as client:
            if not await client.is_user_authorized():
                logger.error("Invalid session string.")
                print("Invalid session string. Generate a new one using generate_session.py.")
                return

            all_configs = {"vless": [], "vmess": [], "shadowsocks": [], "trojan": []}
            all_operator_configs = defaultdict(list)
            all_proxies = []
            all_npvt_files = []
            channel_recent_configs = {}
            channel_recent_npvt = {}
            channel_recent_proxies = {}
            valid_channels = []

            for channel in TELEGRAM_CHANNELS:
                logger.info(f"Fetching configs/proxies from {channel}...")
                print(f"\n📡 Fetching from {channel}...")
                try:
                    channel_configs, channel_config_timeline, channel_operator_configs, channel_proxies, channel_npvt_files, channel_proxy_timeline, is_valid = await fetch_configs_and_proxies_from_channel(client, channel)
                    if not is_valid:
                        print(f"⚠️  [{channel}] Invalid or inaccessible")
                        invalid_channels.append(channel)
                        channel_stats[channel] = {
                            "vless_count": 0,
                            "vmess_count": 0,
                            "shadowsocks_count": 0,
                            "trojan_count": 0,
                            "proxy_count": 0,
                            "total_configs": 0,
                            "score": 0,
                            "error": "Channel does not exist or is inaccessible"
                        }
                        continue

                    valid_channels.append(channel)
                    total_configs = sum(len(configs) for configs in channel_configs.values())
                    proxy_count = len(channel_proxies)
                    score = total_configs + proxy_count
                    print(f"   └─ vless: {len(channel_configs['vless'])} | vmess: {len(channel_configs['vmess'])} | ss: {len(channel_configs['shadowsocks'])} | trojan: {len(channel_configs['trojan'])} | proxies: {proxy_count} | npvt: {len(channel_npvt_files)}")

                    channel_stats[channel] = {
                        "vless_count": len(channel_configs["vless"]),
                        "vmess_count": len(channel_configs["vmess"]),
                        "shadowsocks_count": len(channel_configs["shadowsocks"]),
                        "trojan_count": len(channel_configs["trojan"]),
                        "proxy_count": proxy_count,
                        "total_configs": total_configs,
                        "score": score
                    }

                    for protocol in all_configs:
                        all_configs[protocol].extend(channel_configs[protocol])
                    for op in channel_operator_configs:
                        all_operator_configs[op].extend(channel_operator_configs[op])

                    all_proxies.extend(channel_proxies)
                    all_npvt_files.extend([item["file_path"] for item in channel_npvt_files])
                    channel_recent_configs[channel] = channel_config_timeline
                    channel_recent_npvt[channel] = channel_npvt_files
                    channel_recent_proxies[channel] = channel_proxy_timeline
                except Exception as e:
                    print(f"❌ [{channel}] Exception: {str(e)}")
                    invalid_channels.append(channel)
                    channel_stats[channel] = {
                        "vless_count": 0,
                        "vmess_count": 0,
                        "shadowsocks_count": 0,
                        "trojan_count": 0,
                        "proxy_count": 0,
                        "total_configs": 0,
                        "score": 0,
                        "error": str(e)
                    }
                    logger.error(f"Channel {channel} is invalid: {str(e)}")

            print("\n" + "=" * 60)
            for protocol in all_configs:
                all_configs[protocol] = list(set(all_configs[protocol]))
                print(f"📊 Found {len(all_configs[protocol])} unique {protocol.upper()} configs")
                logger.info(f"Found {len(all_configs[protocol])} unique {protocol} configs")
            for op in all_operator_configs:
                all_operator_configs[op] = list(set(all_operator_configs[op]))
                print(f"📊 Found {len(all_operator_configs[op])} configs for {op}")
                logger.info(f"Found {len(all_operator_configs[op])} unique configs for operator {op}")

            all_proxies = list(dict.fromkeys(all_proxies))
            all_npvt_files = list(dict.fromkeys(all_npvt_files))
            print(f"📊 Found {len(all_proxies)} unique proxies")
            print(f"📊 Found {len(all_npvt_files)} downloaded NPVT files")
            print("=" * 60 + "\n")

            for protocol in all_configs:
                save_configs(all_configs[protocol], protocol)
            save_operator_configs(all_operator_configs)
            save_proxies(all_proxies)
            save_invalid_channels(invalid_channels)
            save_channel_stats(channel_stats)

            await post_config_and_proxies_to_channel(
                client,
                channel_stats,
                valid_channels,
                channel_recent_configs,
                channel_recent_npvt,
                channel_recent_proxies
            )
            update_channels(valid_channels)

    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        print(f"Error in main loop: {str(e)}")
        return

    logger.info("Config+proxy collection process completed")
    print("✅ Config+proxy collection process completed!")


if __name__ == "__main__":
    asyncio.run(main())
