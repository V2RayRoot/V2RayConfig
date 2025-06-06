# V2RayConfig

این پروژه به صورت خودکار کانفیگ‌های V2Ray رو از کانال‌های تلگرامی هر ۳۰ دقیقه یک‌بار با استفاده از GitHub Actions جمع‌آوری می‌کنه و بهترین کانفیگ رو توی کانال @V2RayRootFree منتشر می‌کنه.

**[نسخه انگلیسی (English)](README.md)**

## فایل‌های کانفیگ

| پروتکل       | لینک                           |
|---------------|--------------------------------|
| VLESS         | [`Config/vless.txt`](Config/vless.txt)         |
| VMess         | [`Config/vmess.txt`](Config/vmess.txt)         |
| Shadowsocks   | [`Config/shadowsocks.txt`](Config/shadowsocks.txt) |

## کانال‌های تلگرام

لیست کانال‌های تلگرامی به صورت پویا به‌روزرسانی می‌شه و توی فایل [`telegram_channels.json`](telegram_channels.json) ذخیره می‌شه. کانال‌هایی که نامعتبر بشن به صورت خودکار از این لیست حذف می‌شن.

## آمار کانال‌ها

فایل [`Logs/channel_stats.json`](Logs/channel_stats.json) شامل آمار هر کانال می‌شه، از جمله:
- تعداد کانفیگ‌های VLESS، VMess و Shadowsocks که پیدا شدن.
- تعداد کل کانفیگ‌ها (`total_configs`).
- یه امتیاز (`score`) که برابر با تعداد کل کانفیگ‌هاست و برای انتخاب بهترین کانال برای انتشار کانفیگ‌ها استفاده می‌شه.

می‌تونید از این فایل استفاده کنید تا ببینید کدوم کانال‌ها بیشترین تعداد کانفیگ رو ارائه می‌دن.

## نکات

- کانفیگ‌ها هر ۳۰ دقیقه به‌روزرسانی می‌شن.
- بهترین کانفیگ توی کانال تلگرامی @V2RayRootFree منتشر می‌شه.
- ممکنه برخی کانال‌ها نامعتبر باشن یا کانفیگی نداشته باشن. برای جزئیات، فایل `Logs/invalid_channels.txt` رو می‌تونید بررسی کنید.
- **کانال جدیدی می‌شناسید؟** اگه کانال تلگرامی‌ای می‌شناسید که کانفیگ‌های V2Ray ارائه می‌ده، لطفاً توی بخش [Issues](https://github.com/USERNAME/REPOSITORY/issues) معرفیش کنید تا به لیست اضافه کنیم!
