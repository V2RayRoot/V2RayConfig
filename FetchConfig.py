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

TELEGRAM_CHANNELS = [
    "@V2Line", "@PrivateVPNs", "@VlessConfig", "@V2pedia", "@DailyV2RY",
    "@proxystore11", "@DirectVPN", "@VmessProtocol", "@OutlineVpnOfficial",
    "@networknim", "@beiten", "@MsV2ray", "@foxrayiran", "@yaney_01",
    "@FreakConfig", "@EliV2ray", "@ServerNett", "@v2rayng_fa2",
    "@v2rayng_org", "@V2rayNGvpni", "@custom_14", "@V2rayNG_VPNN",
    "@v2ray_outlineir", "@v2_vmess", "@FreeVlessVpn", "@vmess_vless_v2rayng",
    "@freeland8", "@vmessiran", "@Outline_Vpn", "@vmessq", "@WeePeeN",
    "@V2rayNG3", "@ShadowsocksM", "@shadowsocksshop", "@v2rayan",
    "@ShadowSocks_s", "@hope_net", "@azadnet", "@customv2ray",
    "@nim_vpn_ir", "@outline_vpn", "@fnet00", "@V2rayNG_Matsuri",
    "@proxystore11_2", "@v2rayng_vpn", "@freev2rayconfigs", "@V2RayFast",
    "@ProxyMTProto", "@V2RayHub", "@ConfigV2Ray"
]

OUTPUT_DIR = "v2ray_configs"
INVALID_CHANNELS_FILE = "invalid_channels.txt"
STATS_FILE = "channel_stats.json"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

CONFIG_PATTERNS = {
    "vless": r"vless://[^\s]+",
    "vmess": r"vmess://[^\s]+",
    "shadowsocks": r"ss://[^\s]+"
}

async def fetch_configs_from_channel(client, channel):
    configs = {"vless": [], "vmess": [], "shadowsocks": []}
    try:
        async for message in client.iter_messages(channel, limit=100):
            if isinstance(message, Message) and message.message:
                text = message.message
                for protocol, pattern in CONFIG_PATTERNS.items():
                    matches = re.findall(pattern, text)
                    configs[protocol].extend(matches)
        logger.info(f"Fetched {sum(len(v) for v in configs.values())} configs from {channel}")
        return configs
    except Exception as e:
        logger.error(f"Failed to fetch from {channel}: {str(e)}")
        return configs

def save_configs(configs, protocol):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"{protocol}_configs_{timestamp}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        for config in configs:
            f.write(config + "\n")
    logger.info(f"Saved {len(configs)} {protocol} configs to {output_file}")

def save_invalid_channels(invalid_channels):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"{INVALID_CHANNELS_FILE}_{timestamp}.txt", "w", encoding="utf-8") as f:
        for channel in invalid_channels:
            f.write(f"{channel}\n")
    logger.info(f"Saved {len(invalid_channels)} invalid channels to {INVALID_CHANNELS_FILE}_{timestamp}.txt")

def save_channel_stats(stats):
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

    session = StringSession(SESSION_STRING)
    
    async with TelegramClient(session, api_id=1, api_hash="dummy") as client:
        if not await client.is_user_authorized():
            logger.error("Invalid session string.")
            print("Invalid session string. Generate a new one using generate_session.py.")
            return

        all_configs = {"vless": [], "vmess": [], "shadowsocks": []}
        for channel in TELEGRAM_CHANNELS:
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

        for protocol, configs in all_configs.items():
            if configs:
                save_configs(configs, protocol)
            else:
                logger.warning(f"No {protocol} configs found")

        if invalid_channels:
            save_invalid_channels(invalid_channels)

        save_channel_stats(channel_stats)

        session_str = session.save()
        print(f"Session string (save this in GitHub Secrets as TELEGRAM_SESSION_STRING):\n{session_str}")

    logger.info("Config collection process completed")

if __name__ == "__main__":
    asyncio.run(main())
