# ایجنت کدنویس چند-عاملی (n8n + C# sandbox)

پروژه نهایی: یک Coding Agent روی n8n که درخواست متنی را به برنامه تبدیل می‌کند، از انسان تأیید/بازخورد می‌گیرد، کد C# تولید می‌کند، آن را در Docker واقعاً اجرا می‌کند، تا ۳ بار با خطای واقعی اصلاح می‌کند، روی GitHub PR می‌سازد و گزارش Markdown می‌دهد.

شرح اتصال نودها، حلقه‌ها و نحوهٔ اجرا: [ARCHITECTURE.md](./ARCHITECTURE.md)

## ورک‌فلو

- اینستنس: `https://n8n.denox.ir/workflow/LkpwmWAnSXuBzQ8q`
- فرم شروع (فعال): `https://n8n.denox.ir/form/coding-agent`
- تأیید انسان: نود Telegram با credential `Bale account` به چت `1753826181` (`sendAndWait`)
- مدل همه عامل‌ها: `gpt-5.6-luna` با credential موجود `OpenAI account Proxy`
- حافظه بلندمدت: Data Table `coding_agent_memory`
- ریپوی خروجی کد تولیدشده: [ashkandehnavi/n8n-code](https://github.com/ashkandehnavi/n8n-code)
- سورس این پروژه (برنچ جدا): [final-exam/coding-agent](https://github.com/ashkandehnavi/n8n-code/tree/final-exam/coding-agent)

## نقش‌ها

| عامل | مسئولیت |
| --- | --- |
| Planner | تجزیه درخواست به برنامه JSON |
| Human-in-the-loop | توقف بعد از Planner؛ پیام به بله (Telegram + Bale account) و انتظار پاسخ متنی |
| Coder | تولید پروژه کامل .NET 8 |
| Reviewer / Tester | قضاوت روی خروجی واقعی sandbox |
| Fixer | اصلاح بر اساس stderr/stdout واقعی؛ حداکثر ۳ بار |

محدودیت کل ورک‌فلو: ۱۵ دقیقه. Timeout هر اجرا در sandbox: ۶۰ ثانیه. حافظه کانتینر: ۱GB.

## اجرای sandbox

n8n روی denox به `https://sandbox.denox.ir` وصل می‌شود (پروکسی به Docker روی پورت 8099). تونل Cloudflare لازم نیست.

برای اجرای محلی کانتینر:

```powershell
.\scripts\start-sandbox.ps1
```

- UI محلی: `http://127.0.0.1:8099`
- آدرس عمومی برای n8n: `https://sandbox.denox.ir`

## ساختار

```
sandbox/          وب‌اپ سندباکس (UI + API اجرای C# + publish گیت‌هاب)
                   محلی: http://127.0.0.1:8099
                   عمومی: https://sandbox.denox.ir
n8n/              خروجی JSON ورک‌فلو
scripts/          ساخت و آپلود ورک‌فلو
```

ویدئوی ۱۵ دقیقه‌ای طبق درخواست در این پیاده‌سازی نیست.
