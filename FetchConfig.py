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
DESTINATION_CHANNEL = "@V2RayRoot"
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
    operator_configs = defaultdict(list)
    proxies = []
    npvt_files = []
    try:
        channel_entity = await resolve_channel_target(client, channel)
    except (ChannelInvalidError, PeerIdInvalidError, ValueError) as e:
        logger.error(f"Channel {channel} does not exist or is inaccessible: {str(e)}")
        return configs, operator_configs, proxies, npvt_files, False
    except Exception as e:
        logger.error(f"Channel {channel} could not be resolved: {str(e)}")
        return configs, operator_configs, proxies, npvt_files, False

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
                npvt_files.append(downloaded_npvt)

            if isinstance(message, Message) and message.message:
                text = message.message

                operator = detect_operator(text)

                for protocol, pattern in CONFIG_PATTERNS.items():
                    matches = re.findall(pattern, text)
                    if matches:
                        logger.info(f"[{channel}] Found {len(matches)} {protocol} configs in message {message.id}")
                        print(f"✅ [{channel}] Found {len(matches)} {protocol} configs")
                        configs[protocol].extend(matches)
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
        
        summary = f"[{channel}] ✔️ Processed {message_count} messages → Found {configs_found_count} configs + {len(proxies)} proxies + {len(npvt_files)} npvt"
        logger.info(summary)
        print(summary)
        return configs, operator_configs, proxies, npvt_files, True
    except Exception as e:
        logger.error(f"Failed to fetch from {channel}: {str(e)}")
        print(f"❌ [{channel}] Error: {str(e)}")
        return configs, operator_configs, proxies, npvt_files, False

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

async def send_message_to_destination(client, destination, message, parse_mode="markdown"):
    try:
        if isinstance(destination, str):
            dest_identifier = await resolve_channel_target(client, destination)
        else:
            dest_identifier = destination
        
        await client.send_message(dest_identifier, message, parse_mode=parse_mode)
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

        await client.send_file(dest_identifier, file_path, caption=caption, parse_mode=parse_mode)
        logger.info(f"Successfully sent file to {destination}: {file_path}")
        print(f"✅ File posted to {destination}: {os.path.basename(file_path)}")
        return True
    except Exception as e:
        logger.error(f"Failed to send file to {destination}: {str(e)}")
        print(f"❌ Failed to send file to {destination}: {str(e)}")
        return False

async def post_config_and_proxies_to_channel(client, all_configs, all_proxies, all_npvt_files, channel_stats):
    if not channel_stats:
        logger.warning("No channel stats available to determine the best channel.")
        print("⚠️  No channel stats available")
        return

    best_channel = None
    best_score = -1
    for channel, stats in channel_stats.items():
        score = stats.get("score", 0)
        if score > best_score:
            best_score = score
            best_channel = channel

    if not best_channel or best_score == 0:
        logger.warning("No valid channel with configs found to post.")
        print("⚠️  No valid channel with configs found")
        return

    try:
        destination_entity = await resolve_channel_target(client, DESTINATION_CHANNEL)
    except Exception as e:
        logger.error(f"Failed to resolve destination channel {DESTINATION_CHANNEL}: {str(e)}")
        print(f"❌ Failed to resolve destination channel: {str(e)}")
        return

    channel_configs = {"vless": [], "vmess": [], "shadowsocks": [], "trojan": []}
    channel_proxies = []
    try:
        temp_configs, _, temp_proxies, _, _ = await fetch_configs_and_proxies_from_channel(client, best_channel)
        for protocol in channel_configs:
            channel_configs[protocol].extend(temp_configs[protocol])
        channel_proxies.extend(temp_proxies)
    except Exception as e:
        logger.error(f"Failed to fetch configs/proxies from best channel {best_channel}: {str(e)}")
        print(f"❌ Failed to fetch from {best_channel}: {str(e)}")
        return

    all_channel_configs = []
    config_types = []
    for protocol in channel_configs:
        for config in channel_configs[protocol]:
            all_channel_configs.append(config)
            config_types.append(protocol.capitalize())

    if not all_channel_configs:
        logger.warning(f"No configs found from the best channel {best_channel} to post.")
        print(f"⚠️  No configs from {best_channel}")
        return

    # index = random.randint(0, len(all_channel_configs) - 1)
    # selected_config = all_channel_configs[index]
    # config_type = config_types[index]

    # message = f"⚙️🌐 {config_type} Config\n\n```{selected_config}```"

    # random.shuffle(all_proxies)
    # fresh_proxies = all_proxies[:8] if len(all_proxies) >= 8 else all_proxies
    # if fresh_proxies:
    #     proxies_formatted = format_proxies_in_rows(fresh_proxies, per_row=4)
    #     message += "\n" + proxies_formatted

    # message += "\n\n🆔 @V2RayRootFree"

    # success = await send_message_to_destination(client, DESTINATION_CHANNEL, message, parse_mode="markdown")
    
    # if success:
    #     logger.info(f"Posted {config_type} config + proxies from {best_channel} to {DESTINATION_CHANNEL}")
    #     print(f"📤 Posted {config_type} config from {best_channel}")
    # else:
    #     logger.error(f"Failed to post to {DESTINATION_CHANNEL}")

    POST_COUNT = 5
    
    random_indices = random.sample(
        range(len(all_channel_configs)),
        min(POST_COUNT, len(all_channel_configs))
    )

    shuffled_npvt = list(all_npvt_files)
    random.shuffle(shuffled_npvt)
    
    for i, idx in enumerate(random_indices, start=1):
        selected_config = all_channel_configs[idx]
        config_type = config_types[idx]
    
        message = f"⚙️🌐 {config_type} Config ({i}/{len(random_indices)})\n\n```{selected_config}```"
    
        random.shuffle(all_proxies)
        fresh_proxies = all_proxies[:8] if len(all_proxies) >= 8 else all_proxies
        if fresh_proxies:
            proxies_formatted = format_proxies_in_rows(fresh_proxies, per_row=4)
            message += "\n" + proxies_formatted
    
        message += "\n\n🆔 @V2RayRootFree"
    
        if shuffled_npvt:
            npvt_file = shuffled_npvt[(i - 1) % len(shuffled_npvt)]
            success = await send_file_to_destination(
                client,
                destination_entity,
                npvt_file,
                message,
                parse_mode="markdown"
            )
        else:
            success = await send_message_to_destination(
                client,
                destination_entity,
                message,
                parse_mode="markdown"
            )
    
        if success:
            logger.info(f"Posted {config_type} config {i}")
            print(f"📤 Posted config {i}")
        else:
            logger.error(f"Failed to post config {i}")
    
        await asyncio.sleep(8)


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
            valid_channels = []
            for channel in TELEGRAM_CHANNELS:
                logger.info(f"Fetching configs/proxies from {channel}...")
                print(f"\n📡 Fetching from {channel}...")
                try:
                    channel_configs, channel_operator_configs, channel_proxies, channel_npvt_files, is_valid = await fetch_configs_and_proxies_from_channel(client, channel)
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
                    all_npvt_files.extend(channel_npvt_files)
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

            print("\n" + "="*60)
            for protocol in all_configs:
                all_configs[protocol] = list(set(all_configs[protocol]))
                print(f"📊 Found {len(all_configs[protocol])} unique {protocol.upper()} configs")
                logger.info(f"Found {len(all_configs[protocol])} unique {protocol} configs")
            for op in all_operator_configs:
                all_operator_configs[op] = list(set(all_operator_configs[op]))
                print(f"📊 Found {len(all_operator_configs[op])} configs for {op}")
                logger.info(f"Found {len(all_operator_configs[op])} unique configs for operator {op}")
            all_proxies = list(set(all_proxies))
            all_npvt_files = list(dict.fromkeys(all_npvt_files))
            print(f"📊 Found {len(all_proxies)} unique proxies")
            print(f"📊 Found {len(all_npvt_files)} downloaded NPVT files")
            print("="*60 + "\n")

            for protocol in all_configs:
                save_configs(all_configs[protocol], protocol)
            save_operator_configs(all_operator_configs)
            save_proxies(all_proxies)
            save_invalid_channels(invalid_channels)
            save_channel_stats(channel_stats)
            await post_config_and_proxies_to_channel(client, all_configs, all_proxies, all_npvt_files, channel_stats)
            update_channels(valid_channels)

    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        print(f"Error in main loop: {str(e)}")
        return

    logger.info("Config+proxy collection process completed")
    print("✅ Config+proxy collection process completed!")

if __name__ == "__main__":
    asyncio.run(main())
