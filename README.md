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

The list of Telegram channels is dynamically updated and stored in [`Logs/telegram_channels.json`](Logs/telegram_channels.json). Channels that become invalid are automatically removed from this list.

## Notes

- Configurations are updated every 30 minutes.
- The best config is posted to the Telegram channel @V2RayRootFree.
- Some channels may be invalid or contain no configs. Check `Logs/invalid_channels.txt` for details.
