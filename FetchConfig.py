import os
import re
import json
import logging
from datetime import datetime
from telethon.sync import TelegramClient
from telethon.tl.types import Message
import asyncio
from telethon.sessions import StringSession


logging.basicConfig(
    filename="collector.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()


SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", None)
API_ID = os.getenv("TELEGRAM_API_ID", None)
API_HASH = os.getenv("TELEGRAM_API_HASH", None)


TELEGRAM_CHANNELS = [
    "@V2RayNGn", "@V2RayNG_VPN", "@FreeV2rayChannel", "@V2RayNG_Config", "@V2RayNG_Configs",
    "@V2RayN_VPN", "@V2RayNG_Iran", "@V2RayNG_V2Ray", "@V2RayNG_Fast", "@V2RayNG_Pro",
    "@V2RayNG_Store", "@V2RayNG_Club", "@V2RayNG_Premium", "@V2RayNG_Elite", "@V2RayNG_Master",
    "@V2RayNG_Expert", "@V2RayNG_Star", "@V2RayNG_Power", "@V2RayNG_Sky", "@V2RayNG_Gold",
    "@V2RayNG_Diamond", "@V2RayNG_Platinum", "@V2RayNG_Silver", "@V2RayNG_Bronze", "@V2RayNG_Iron",
    "@V2RayNG_Steel", "@V2RayNG_Copper", "@V2RayNG_Titanium", "@V2RayNG_Aluminum", "@V2RayNG_Zinc",
    "@V2RayNG_Nickel", "@V2RayNG_Chrome", "@V2RayNG_Metal", "@V2RayNG_Fire", "@V2RayNG_Water",
    "@V2RayNG_Earth", "@V2RayNG_Air", "@V2RayNG_Spirit", "@V2RayNG_Light", "@V2RayNG_Dark",
    "@V2RayNG_Shadow", "@V2RayNG_Ghost", "@V2RayNG_Phantom", "@V2RayNG_Specter", "@V2RayNG_Wraith",
    "@V2RayNG_Banshee", "@V2RayNG_Vampire", "@V2RayNG_Werewolf", "@V2RayNG_Zombie", "@V2RayNG_Dragon"
]


OUTPUT_DIR = "Config"
INVALID_CHANNELS_FILE = "invalid_channels.txt"
STATS_FILE = "channel_stats.json"


if not os.path.exists(OUTPUT_DIR):
    logger.info(f"Creating directory: {OUTPUT_DIR}")
    os.makedirs(OUTPUT_DIR)


CONFIG_PATTERNS = {
    "vless": r"vless://[^\s]+",
    "vmess": r"vmess://[^\s]+",
    "shadowsocks": r"ss://[^\s]+"
}

async def fetch_configs_from_channel(client, channel):
    configs = {"vless": [], "vmess": [], "shadowsocks": []}
    try:
        message_count = 0
        async for message in client.iter_messages(channel, limit=200):
            message_count += 1
            if isinstance(message, Message) and message.message:
                text = message.message
                for protocol, pattern in CONFIG_PATTERNS.items():
                    matches = re.findall(pattern, text)
                    if matches:
                        logger.info(f"Found {len(matches)} {protocol} configs in message from {channel}: {matches}")
                        configs[protocol].extend(matches)
        logger.info(f"Processed {message_count} messages from {channel}, found {sum(len(v) for v in configs.values())} configs")
        return configs
    except Exception as e:
        logger.error(f"Failed to fetch from {channel}: {str(e)}")
        return configs

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

def save_invalid_channels(invalid_channels):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{INVALID_CHANNELS_FILE}_{timestamp}.txt"
    logger.info(f"Saving invalid channels to {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        if invalid_channels:
            for channel in invalid_channels:
                f.write(f"{channel}\n")
            logger.info(f"Saved {len(invalid_channels)} invalid channels to {output_file}")
        else:
            f.write("No invalid channels found.\n")
            logger.info(f"No invalid channels found, wrote placeholder to {output_file}")

def save_channel_stats(stats):
    logger.info(f"Saving channel stats to {STATS_FILE}")
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=4)
    logger.info(f"Saved channel stats to {STATS_FILE}")

async def main():
    logger.info("Starting config collection process")
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

    session = StringSession(SESSION_STRING)
    
    
    try:
        async with TelegramClient(session, api_id, API_HASH) as client:
            if not await client.is_user_authorized():
                logger.error("Invalid session string.")
                print("Invalid session string. Generate a new one using generate_session.py.")
                return

            
            all_configs = {"vless": [], "vmess": [], "shadowsocks": []}
            for channel in TELEGRAM_CHANNELS:
                logger.info(f"Fetching configs from {channel}...")
                print(f"Fetching configs from {channel}...")
                try:
                    channel_configs = await fetch_configs_from_channel(client, channel)
                    total_configs = sum(len(configs) for configs in channel_configs.values())
                    channel_stats[channel] = {
                        "vless_count": len(channel_configs["vless"]),
                        "vmess_count": len(channel_configs["vmess"]),
                        "shadowsocks_count": len(channel_configs["shadowsocks"]),
                        "total_configs": total_configs,
                        "score": total_configs
                    }
                    for protocol in all_configs:
                        all_configs[protocol].extend(channel_configs[protocol])
                except Exception as e:
                    invalid_channels.append(channel)
                    channel_stats[channel] = {
                        "vless_count": 0,
                        "vmess_count": 0,
                        "shadowsocks_count": 0,
                        "total_configs": 0,
                        "score": 0,
                        "error": str(e)
                    }
                    logger.error(f"Channel {channel} is invalid: {str(e)}")

            
            for protocol in all_configs:
                all_configs[protocol] = list(set(all_configs[protocol]))
                logger.info(f"Found {len(all_configs[protocol])} unique {protocol} configs")

            
            for protocol in all_configs:
                save_configs(all_configs[protocol], protocol)

            
            save_invalid_channels(invalid_channels)

            
            save_channel_stats(channel_stats)

    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        print(f"Error in main loop: {str(e)}")
        return

    logger.info("Config collection process completed")

if __name__ == "__main__":
    asyncio.run(main())
