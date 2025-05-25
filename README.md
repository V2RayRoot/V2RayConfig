# V2RayConfig

This project automatically fetches V2Ray configurations from Telegram channels every 30 minutes using GitHub Actions and posts the best config to @V2RayRootFree.

**[نسخه فارسی (Persian)](README.fa.md)**

## Configuration Files

| Protocol      | Link                           |
|---------------|--------------------------------|
| VLESS         | [`Config/vless.txt`](Config/vless.txt)         |
| VMess         | [`Config/vmess.txt`](Config/vmess.txt)         |
| Shadowsocks   | [`Config/shadowsocks.txt`](Config/shadowsocks.txt) |

## Telegram Channels

The list of Telegram channels is dynamically updated and stored in [`telegram_channels.json`](telegram_channels.json). Channels that become invalid are automatically removed from this list.

## Channel Statistics

The file [`Logs/channel_stats.json`](Logs/channel_stats.json) contains statistics for each channel, including:
- The number of VLESS, VMess, and Shadowsocks configs found.
- The total number of configs (`total_configs`).
- A score (`score`), which is equal to the total number of configs, used to determine the best channel for posting configs.

You can use this file to see which channels are providing the most configs.

## Notes

- Configurations are updated every 30 minutes.
- The best config is posted to the Telegram channel @V2RayRootFree.
- Some channels may be invalid or contain no configs. Check `Logs/invalid_channels.txt` for details.
- **Know a new channel?** If you know a Telegram channel that provides V2Ray configs, please share it in the [Issues](https://github.com/USERNAME/REPOSITORY/issues) section, and we'll add it to the list!
