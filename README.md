# V2RayConfig

This project automatically fetches V2Ray configurations from Telegram channels every 5 minutes using GitHub Actions.

**[نسخه فارسی (Persian)](README.fa.md)**

## Configuration Files

| Protocol      | Link                           |
|---------------|--------------------------------|
| VLESS         | [`Config/vless.txt`](Config/vless.txt)         |
| VMess         | [`Config/vmess.txt`](Config/vmess.txt)         |
| Shadowsocks   | [`Config/shadowsocks.txt`](Config/shadowsocks.txt) |

## Telegram Channels

The configurations are fetched from the following Telegram channels:

|               |               |               |               |
|---------------|---------------|---------------|---------------|
| @V2RayNGn     | @V2RayNG_VPN  | @FreeV2rayChannel | @V2RayNG_Config |
| @V2RayNG_Configs | @V2RayN_VPN   | @V2RayNG_Iran | @V2RayNG_V2Ray |
| @V2RayNG_Fast | @V2RayNG_Pro  | @V2RayNG_Store| @V2RayNG_Club  |
| @V2RayNG_Premium | @V2RayNG_Elite | @V2RayNG_Master | @V2RayNG_Expert |
| @V2RayNG_Star | @V2RayNG_Power | @V2RayNG_Sky  | @V2RayNG_Gold  |
| @V2RayNG_Diamond | @V2RayNG_Platinum | @V2RayNG_Silver | @V2RayNG_Bronze |
| @V2RayNG_Iron | @V2RayNG_Steel | @V2RayNG_Copper | @V2RayNG_Titanium |
| @V2RayNG_Aluminum | @V2RayNG_Zinc | @V2RayNG_Nickel | @V2RayNG_Chrome |
| @V2RayNG_Metal | @V2RayNG_Fire | @V2RayNG_Water | @V2RayNG_Earth |
| @V2RayNG_Air  | @V2RayNG_Spirit | @V2RayNG_Light | @V2RayNG_Dark  |
| @V2RayNG_Shadow | @V2RayNG_Ghost | @V2RayNG_Phantom | @V2RayNG_Specter |
| @V2RayNG_Wraith | @V2RayNG_Banshee | @V2RayNG_Vampire | @V2RayNG_Werewolf |
| @V2RayNG_Zombie | @V2RayNG_Dragon |               |               |

## Notes

- Configurations are updated every 5 minutes.
- Some channels may be invalid or contain no configs. Check `Logs/invalid_channels.txt` for details.
