# 01 — ساخت اولین CI/CD Pipeline واقعی با GitLab 🚀

**موضوع:** Build، تست رفتار واقعی اپلیکیشن، ساخت Docker Image و تست اجرای کانتینر

**پروژه:** `Safe Deployment From Zero` — آموزش عملی برای جامعه NetworksComputing / Sananet

[بازگشت به README اصلی](../README.md)

---

## قراره چی بسازیم؟

فرض کن یک فروشگاه اینترنتی داری که مشتری از طریق API سفارش ثبت می‌کند. تو بخش محاسبه مبلغ سبد خرید را تغییر می‌دهی و کد را `push` می‌کنی. اگر اشتباهی قیمت دو عدد محصول را فقط یک‌بار حساب کرده باشی، سرویس ممکن است روشن باشد و `/health` هم پاسخ `200` بدهد، اما **منطق خرید اشتباه شده است**.

این آزمایش نشان می‌دهد چطور قبل از ساخت و انتشار Docker Image، با **تست‌های واقعی منطق Checkout** چنین خطایی را پیدا کنیم.

> در این مرحله هنوز چیزی روی Production یا Staging منتشر نمی‌کنیم. Pipeline فقط کد را تست می‌کند، Image می‌سازد، در GitLab Container Registry ذخیره می‌کند و همان Image ساخته‌شده را در یک کانتینر موقت بالا می‌آورد و Smoke Test می‌کند. انتشار روی محیط واقعی در مراحل بعدی مطرح می‌شود.

### خروجی نهایی

```text
Git Push
   │
   ▼
[ TEST ]   Python unit tests + HTTP integration tests
   │       اگر تست شکست بخورد، مراحل بعدی اجرا نمی‌شوند
   ▼
[ BUILD ]  docker build → GitLab Container Registry
   │
   ▼
[ SMOKE ]  docker run → Health + Catalog + Checkout requests
   │
   ▼
✅ Image بررسی‌شده، آماده بررسی برای مراحل انتشار بعدی
```

## فایل‌های پروژه کجا هستند؟

از آنجا که در ادامه همین اپلیکیشن را در Staging، Canary و Rollback هم استفاده می‌کنیم، سورس اپلیکیشن در دایرکتوری مشترک `demo-app/` قرار دارد.

```text
safe-deployment-from-zero/
├── README.md
├── .gitlab-ci.yml                  # نقطه ورود GitLab CI/CD در ریشه ریپو
├── demo-app/                       # سورس کامل اپلیکیشن مشترک
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── Makefile
│   ├── app/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── catalog.py              # کاتالوگ محصولات
│   │   ├── checkout.py             # منطق محاسبه سفارش (مهم‌ترین بخش تست)
│   │   └── server.py               # API با Python Standard Library
│   ├── tests/
│   │   ├── test_checkout.py        # Unit Tests
│   │   └── test_api.py             # Integration Tests روی HTTP واقعی
│   └── scripts/
│       └── smoke_test.py           # Smoke Test روی کانتینر اجراشده
└── 01-ci-cd/
    ├── README.md                   # همین آموزش
    └── pipeline.yml               # منطق اصلی GitLab Pipeline
```

> برای سادگی، این نمونه از پایتون بدون هیچ وابستگی خارجی استفاده می‌کند. خود API آموزشی است؛ پرداخت واقعی انجام نمی‌دهد، اطلاعات سفارش را ذخیره نمی‌کند و جایگزین سرویس Production نیست.

## پیش‌نیازها

- برای اجرای محلی بدون Docker: **Python 3.12** (نسخه‌های نزدیک ممکن است کار کنند، اما مثال بر اساس 3.12 نوشته شده)
- برای ساخت و اجرای Image: **Docker Engine / Docker Desktop**
- برای Pipeline: یک پروژه GitLab، **Container Registry فعال** و یک **GitLab Runner** که بتواند Docker-in-Docker را اجرا کند
- دانش ابتدایی `git`, `curl` و HTTP

**نکته امنیتی Runner:** نمونه Pipeline برای ساده‌ترشدن آزمایش، Docker-in-Docker را روی پورت داخلی `2375` و بدون TLS تنظیم می‌کند. این روش باید فقط روی Runner مورداعتماد و ایزوله با پشتیبانی `privileged` استفاده شود؛ برای محیط حساس یا Runner مشترکِ خودمدیریت‌شده، تنظیم TLS و ایزوله‌سازی مناسب را طبق مستندات GitLab انتخاب کنید. هیچ پورتی از Docker daemon را روی اینترنت باز نکنید.

مستندات رسمی:
- [GitLab: Docker-in-Docker](https://docs.gitlab.com/ci/docker/docker_in_docker/)
- [GitLab: Docker image builds](https://docs.gitlab.com/ci/docker/using_docker_build/)
- [GitLab: Registry authentication](https://docs.gitlab.com/user/packages/container_registry/authenticate_with_container_registry/)

---

## قدم ۱ — اپلیکیشن را بشناسیم

این API سه Endpoint دارد:

| Endpoint | متد | کاربرد |
|---|---|---|
| `/health` | GET | فقط اعلام می‌کند سرویس پاسخ‌گوست |
| `/api/products` | GET | لیست محصولات و قیمت‌ها |
| `/api/checkout` | POST | اعتبارسنجی سبد خرید و محاسبه جمع، هزینه ارسال و مبلغ نهایی |

قیمت‌ها در نمونه با واحد **سنت دلار (integer cents)** نگهداری می‌شوند تا خطاهای محاسباتی اعداد اعشاری پیش نیاید.

فروشگاه نمونه:

| SKU | نام | قیمت |
|---|---|---|
| `keyboard` | Mechanical Keyboard | `4500` سنت |
| `mouse` | Wireless Mouse | `2500` سنت |
| `pad` | Mouse Pad | `1200` سنت |

اگر جمع خرید به `10000` سنت برسد، ارسال رایگان است؛ در غیر این صورت `599` سنت به سفارش اضافه می‌شود.

نمونه درخواست:

```json
{
  "items": [
    {"sku": "keyboard", "quantity": 2},
    {"sku": "mouse", "quantity": 1}
  ]
}
```

نتیجه موردانتظار: `2 × 4500 + 2500 = 11500` سنت؛ بنابراین هزینه ارسال `0` و مبلغ نهایی `11500` سنت است.

## قدم ۲ — تست محلی کد، بدون Docker

از **ریشه Repository**:

```bash
cd demo-app
python3 -m unittest discover -s tests -v
```

تست‌ها دو دسته‌اند:

**Unit Tests** در `tests/test_checkout.py`:
- محاسبه درست مبلغ برای چند کالا و تعداد متفاوت
- هزینه ارسال کمتر از سقف و رایگان‌شدن در سقف
- رد کردن سبد خالی، SKU ناشناخته و تعداد نامعتبر

**Integration Tests** در `tests/test_api.py`:
- ساخت یک HTTP Server محلی روی پورت تصادفی
- درخواست واقعی HTTP به `/health`، `/api/products` و `/api/checkout`
- بررسی کد وضعیت و پاسخ JSON
- اطمینان از اینکه ورودی اشتباه با `400` رد می‌شود، نه `500`

**انتظار:** همه تست‌ها با `OK` تمام شوند.

### اجرای دستی API

هنوز داخل `demo-app/` هستیم:

```bash
python3 -m app
```

در ترمینال دیگری:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/products
```

و یک درخواست واقعی Checkout:

```bash
curl -s -X POST http://127.0.0.1:8000/api/checkout \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"sku":"keyboard","quantity":2},{"sku":"mouse","quantity":1}]}'
```

در پاسخ باید `"subtotal_cents": 11500` و `"total_cents": 11500` ببینی. برای پایان، `Ctrl+C` بزن.

## قدم ۳ — Docker Image بسازیم و اجرا کنیم

داخل `demo-app/`:

```bash
docker build -t safe-deployment-demo:v1 .
docker run -d --name checkout-demo -p 8000:8000 safe-deployment-demo:v1
```

سپس:

```bash
curl -s http://127.0.0.1:8000/health
python3 scripts/smoke_test.py http://127.0.0.1:8000
```

Smoke Test چهار چیز را بررسی می‌کند: سلامت API، دسترسی به محصولات، محاسبه صحیح Checkout و ردکردن سبد نامعتبر. در پایان باید پیام `SMOKE TEST: ALL PASSED` نمایش داده شود.

پاک‌سازی:

```bash
docker rm -f checkout-demo
```

**تفاوت مهم:** Unit Test منطق برنامه را قبل از Build بررسی می‌کند؛ Smoke Test مطمئن می‌شود Image ساخته‌شده **واقعاً اجرا می‌شود** و مسیرهای حیاتی API در کانتینر کار می‌کنند.

## قدم ۴ — GitLab Pipeline را راه‌اندازی کنیم

۱. کل پوشه `safe-deployment-from-zero/` را به یک پروژه GitLab منتقل کن؛ `.gitlab-ci.yml` باید **در ریشه Repository** باشد.

۲. در GitLab قسمت **Deploy → Container Registry** را بررسی کن و مطمئن شو Registry برای پروژه فعاله. آدرس Image توسط متغیر داخلی `CI_REGISTRY_IMAGE` تأمین می‌شود؛ نباید رمز عبور را در YAML بنویسی.

۳. یک Runner سازگار با Docker-in-Docker لازم است. تنظیمات امنیتی بالا را بخوان. Runner معمولی بدون دسترسی مناسب به Docker ممکن است Jobهای `docker_build` و `container_smoke_test` را اجرا نکند.

۴. Push کن:

```bash
git add .
git commit -m "feat: add checkout CI pipeline lab"
git push
```

۵. در GitLab مسیر **Build → Pipelines** (در برخی نسخه‌ها **CI/CD → Pipelines**) را باز کن. سه Job باید به ترتیب اجرا شوند:

| Job | کار | نتیجه شکست |
|---|---|---|
| `checkout_tests` | اجرای Unit و Integration Test | Build اجرا نمی‌شود |
| `docker_build` | ساخت Image و Push به Registry با Tag منحصربه‌فرد Commit | Smoke اجرا نمی‌شود |
| `container_smoke_test` | Pull همان Image، اجرای کانتینر و تست API | Pipeline قرمز می‌شود؛ Image نیازمند بررسی است |

Image با قالب `ci-<commit-sha>` تگ می‌شود تا Build هر Commit از بقیه مستقل باشد. این مثال **به‌صورت خودکار Production را Deploy نمی‌کند**.

### چرا این‌جا Registry داریم؟

Jobهای GitLab لزوماً روی یک Runner مشترک اجرا نمی‌شوند و Docker daemon هر Job ممکن است جدا باشد. بنابراین نمی‌توان فرض کرد Image ساخته‌شده در Job بعدی هنوز روی همان Docker host وجود دارد. به همین دلیل آن را در `docker_build` به Registry می‌فرستیم و در `container_smoke_test` دوباره Pull می‌کنیم.

---

## قدم ۵ — آزمایش اصلی: یک باگ Checkout وارد کن!

تا این‌جا دیدیم که Pipeline سبز می‌شود. حالا باید نشان دهیم **وقتی کد واقعاً خراب شد، چه اتفاقی می‌افتد**.

۱. در یک Branch آزمایشی، فایل `demo-app/app/checkout.py` را باز کن.

۲. این خط درست را پیدا کن:

```python
line_total_cents = unit_price_cents * quantity
```

۳. موقتاً آن را به این خط **اشتباه** تغییر بده:

```python
line_total_cents = unit_price_cents
```

این تغییر یعنی حتی اگر مشتری دو عدد کیبورد سفارش بدهد، برنامه فقط قیمت یک عدد را حساب می‌کند! API هنوز بالا می‌آید، اما منطق خرید خراب شده است.

۴. اول محلی تست کن:

```bash
cd demo-app
python3 -m unittest discover -s tests -v
```

تست `test_multiple_items_have_correct_quantity_based_totals` باید Fail شود؛ چون انتظار `11500` سنت داریم، اما برنامه مبلغ اشتباه می‌دهد.

۵. حالا همین تغییر را در Branch آزمایشی Push کن. Job `checkout_tests` شکست می‌خورد و مراحل Build و Smoke اصلاً اجرا نمی‌شوند.

> این همان نکته ریلز است: سالم‌بودن HTTP Server به معنی درست‌کارکردن مسیر خرید نیست. تست‌های کسب‌وکار باید قبل از Build جلوی تغییر خراب را بگیرند.

۶. خط صحیح را برگردان و دوباره Push کن. این بار Pipeline باید سبز شود.

**هشدار:** این تغییر عمدی فقط برای آزمایش روی Branch آموزشی است. آن را روی سرویس واقعی اعمال نکن.

## قدم ۶ — چه چیزهایی را باید در پایان فهمیده باشیم؟

- CI با هر Push، تست‌ها را بدون اجرای دستی توسعه‌دهنده انجام می‌دهد.
- Test باید رفتار مهم مشتری را بررسی کند، نه فقط اینکه `/health` برابر `200` است.
- Docker Image **فقط بعد از قبولی تست‌ها** ساخته می‌شود.
- همان Image ساخته‌شده در یک کانتینر موقت مجدداً Smoke Test می‌شود.
- موفقیت Pipeline تضمین صددرصدی برای نبود باگ در Production نیست؛ پوشش تست، محیط اجرا و مانیتورینگ همچنان اهمیت دارند.

## پرسش‌های متداول

**آیا این CD هم هست؟** در این مرحله هنوز Release یا Deployment واقعی نداریم؛ فعلاً CI + Build/Package + Container Smoke Test را ساخته‌ایم. در فصل Staging مرحله انتشار اضافه می‌شود. نام «CI/CD Pipeline» عنوان مسیر کامل آموزشی است.

**آیا برای این مرحله به Kubernetes نیاز داریم؟** نه. فقط Python، Docker و GitLab Runner مناسب.

**اگر Runner دسترسی Docker نداشت چه؟** Unit/Integration Test همچنان قابل اجراست؛ اما Build و Smoke نیازمند Runner/Build Backend سازگار هستند. مشکل دسترسی Docker را با غیرفعال‌کردن ملاحظات امنیتی روی Runner عمومی حل نکن.

**آیا این یک فروشگاه Production-ready است؟** نه. سرویس نمونه تراکنش مالی ندارد، داده پایدار نمی‌کند و سرور Python Standard Library برای این لابراتوار آموزشی انتخاب شده است.

## مرحله بعد

[02 — Staging Environment](../02-staging/): با استفاده از همین اپلیکیشن، محیط Staging و Production آزمایشی مجزا می‌سازیم و انتشار نسخه جدید را قبل از اثرگذاری روی کاربران تست می‌کنیم.

---

NetworksComputing / Sananet — **Safe Deployment From Zero**
