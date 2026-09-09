# Ta'lim yordamchisi — Telegram bot + Mini App

DTM/attestatsiya testlariga tayyorgarlik va maktab o'quvchilari uchun uy vazifasi
yordamchisi. Telegram bot + ichida Mini App (web ilova). To'liq bepul stackda ishlaydi.

## Nima qiladi

- **Ro'yxatga olish (whitelist):** bot faqat egasi yoki adminlar tasdiqlagan
  foydalanuvchilar uchun ishlaydi.
- **Til:** `/start` da bot salomlashib til so'raydi — **o'zbek, rus, ingliz,
  qoraqalpoq**. Til istalgan vaqtda `/language` yoki menyu tugmasi bilan almashadi.
- **Ariza:** yangi foydalanuvchi start bosib, til tanlab, "📝 Ariza qoldirish" orqali
  ism-familiya + telefon raqamini yuboradi. Telegram ID avtomat olinadi. Egasi/adminlar
  arizani tasdiqlaydi yoki foydalanuvchini ID bo'yicha o'z qo'li bilan qo'shadi
  (`/adduser <id>`).
- **Mini App (faqat tasdiqlangan foydalanuvchilar uchun):**
  - 📚 **Test rejimi** — fan → test to'plami → taymer → natija → xatolar ustida ishlash
    → har bir savolga "AI tushuntirsin".
  - ✍️ **Uy vazifasi yordamchisi** — matn yoki rasm yuborasiz, AI qadam-baqadam yechadi.
- **Rollarga ajratilgan interfeys:** oddiy foydalanuvchi admin menyularini **hech qachon
  ko'rmaydi**. Admin panel faqat egasi/adminlarga ochiladi (bot klaviaturasida ham,
  Mini App ichida ham, server tomonda ham qayta tekshiriladi).
- **Admin panel (Mini App ichida):** arizalar, foydalanuvchilar (qo'shish/blok/o'chirish),
  adminlar (faqat ega), **egalikni boshqa adminga topshirish**, obuna sozlamalari,
  test banki CRUD, ommaviy xabar, statistika.
- **Obuna (Telegram Stars ⭐):** egasi/adminlar obuna funksiyasini **istalgan vaqtda
  yoqib-o'chiradi** va rejalarni (kun / ⭐ narx) tahrirlaydi. Yoqilганda AI va test
  topshirish obuna talab qiladi.
- **AI backend sozlanadi:** Groq (bepul), Google Gemini (bepul), yoki o'zingizning
  Ollama serveringiz. Kalit bo'lmasa AI o'chib turadi, qolgan hammasi ishlayveradi.

## Texnologiyalar

Python 3.12 · aiogram 3 · FastAPI · SQLAlchemy 2 (async) · SQLite/Postgres · Telegram
Stars · oddiy HTML/CSS/JS Mini App (build talab qilmaydi).

Bitta jarayon hammasini beradi: bot webhook + Mini App static + JSON API.

---

## 1. Lokal ishga tushirish

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env            # keyin .env ni to'ldiring
python -m scripts.seed_demo       # ixtiyoriy: namuna testlar

uvicorn app.main:app --reload --port 8080
```

`.env` da `USE_POLLING=1` bo'lsa bot **long-polling** rejimida ishlaydi — public URL
shart emas, Telegramda `/start` bosib sinab ko'ring.

> Mini App ni lokal sinash uchun HTTPS kerak. `WEBHOOK_BASE` ni vaqtincha
> [ngrok](https://ngrok.com) / [cloudflared] tunnel URL ga qo'ying yoki to'g'ridan-to'g'ri
> Render'ga deploy qilib sinang.

Testlar:

```bash
pytest -q
```

---

## 2. Bepul serverga (Render.com) deploy

### 2.1. Ma'lumotlar bazasi (bepul, doimiy)

Render'ning bepul disk'i **vaqtinchalik** — restartda yo'qoladi. Shu sabab tashqi bepul
Postgres oling:

- [Neon](https://neon.tech) → yangi project → `Connection string` ni oling
  (`postgresql://...`). Kodi buni avtomat `postgresql+asyncpg://...` ga o'giradi.
- yoki [Supabase](https://supabase.com) → Project → Database → Connection string.

`DATABASE_URL` shu string bo'ladi. (Tez sinov uchun SQLite ham qoldirsa bo'ladi, lekin
ma'lumot restartda o'chadi.)

### 2.2. Bot tokenini yangilash (muhim)

Token setup paytida ochiq matnda yuborilgan. [@BotFather](https://t.me/BotFather) da
`/revoke` → `/token` bilan **yangi token** oling va faqat Render env'ga qo'ying.

### 2.3. Render'da xizmat yaratish

1. Repozitoriyni GitHub'ga push qiling.
2. Render → **New → Blueprint** → repo → `render.yaml` topiladi.
3. `sync: false` bo'lgan env'larni to'ldiring:

   | Kalit | Qiymat |
   |---|---|
   | `BOT_TOKEN` | BotFather'dan yangi token |
   | `OWNER_ID` | `890701906` (allaqachon o'rnatilgan) |
   | `WEBHOOK_BASE` | `https://<xizmat-nomi>.onrender.com` |
   | `DATABASE_URL` | Neon/Supabase connection string |
   | `OPENAI_API_KEY` | Groq kaliti ([console.groq.com](https://console.groq.com)) — ixtiyoriy |
   | `GEMINI_API_KEY` | Google AI Studio kaliti — ixtiyoriy |

   `WEBHOOK_SECRET` va `SESSION_SECRET` avtomat generatsiya bo'ladi.

4. Deploy tugagach, birinchi ishga tushishda bot **avtomat** `setWebhook` qiladi va
   egani (`OWNER_ID`) bazaga yozadi.

### 2.4. BotFather sozlamalari

- `/setmenubutton` → xizmat URL: `https://<xizmat-nomi>.onrender.com/app`
  (Mini App shu tugmadan ochiladi).
- `/setdomain` (ixtiyoriy) → `<xizmat-nomi>.onrender.com`.

### 2.5. Uyqu (cold start) ni kamaytirish

Render bepul xizmat 15 daqiqa harakatsizlikda uxlaydi. [cron-job.org](https://cron-job.org)
yoki [UptimeRobot](https://uptimerobot.com) da har ~10 daqiqada
`https://<xizmat-nomi>.onrender.com/health` ga so'rov qo'ying.

---

## 3. Kundalik ishlatish

### Egasi / adminlar uchun bot buyruqlari

| Buyruq | Kim | Vazifa |
|---|---|---|
| `/pending` | admin | kutilayotgan arizalar (tugmalar bilan) |
| `/adduser <id> [ism]` | admin | foydalanuvchini qo'lda qo'shish |
| `/removeuser <id>` | admin | kirishни bekor qilish |
| `/addadmin <id>` | ega | admin tayinlash |
| `/removeadmin <id>` | ega | adminlikdan olish |
| `/transfer_ownership <id>` | ega | egalikni adminga topshirish (2 bosqichli: `... CONFIRM`) |
| `/subscription [on\|off]` | admin | obuna funksiyasini ko'rish/yoqish/o'chirish |
| `/refund <charge_id>` | admin | Stars to'lovini qaytarish |
| `/broadcast <matn>` | admin | barcha tasdiqlangan foydalanuvchilarga xabar |

Shu amallarning hammasi **Mini App → 🛠 Admin** bo'limида ham bor (qulayroq).

### Test banki

Mini App → Admin → **Kontent**: fan qo'shing → test to'plami qo'shing → savollar
qo'shing (4 til uchun ham nom kiritsangiz bo'ladi; savol matni joriy til bo'yicha
saqlanadi). Yoki `python -m scripts.seed_demo` bilan namuna kontent.

### Obuna

Mini App → Admin → **Obuna**: tumbler bilan yoqing, rejalarni tahrirlang
(kalit / kun / ⭐ narx / nom). Foydalanuvchi Mini App'dagi banner yoki "⭐ Mening obunam"
orqali to'laydi (Telegram Stars).

---

## 4. Loyiha tuzilishi

```
app/
  main.py            FastAPI (webhook + Mini App static + API), lifespan seed
  config.py  db.py  models.py  security.py  i18n.py  locales/{uz,ru,en,kaa}.json
  bot/               aiogram: dispatcher, middlewares, keyboards, states, handlers/
  api/               auth · student · ai · pay · admin  (+ deps: rol/obuna gate)
  services/          users · applications · subscriptions · testbank · ai_service · ...
webapp/              Mini App: index.html · styles.css · app.js
scripts/             set_webhook.py · seed_demo.py
tests/               pytest (i18n parity, initData, rollar, obuna, egalik, testbank)
Dockerfile  render.yaml  .env.example
```

## 5. Xavfsizlik eslatmalari

- `.env` **hech qachon** git'ga tushmaydi (`.gitignore` da). Faqat `.env.example`
  namuna sifatida.
- Webhook: URL ichида maxfiy segment **+** `X-Telegram-Bot-Api-Secret-Token` header
  tekshiruvi.
- Mini App: har so'rovda Telegram `initData` HMAC + `auth_date` muddati tekshiriladi;
  qisqa muddatli imzolangan session token; **har bir admin endpoint** rolni bazadan
  qayta tekshiradi (client'ga ishonilmaydi).
- Setup paytidagi bot tokenini BotFather `/revoke` bilan yangilang.

## 6. AI provayderlar

`.env` da `AI_PROVIDER` (va ixtiyoriy `AI_FALLBACK`): `groq` | `openai` | `gemini` | `ollama`.

- **groq / openai** → `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`
  (Groq: `https://api.groq.com/openai/v1`, model `llama-3.3-70b-versatile`).
- **gemini** → `GEMINI_API_KEY`, `GEMINI_MODEL` (`gemini-2.0-flash`) — rasmli uy
  vazifasini ham qo'llaydi.
- **ollama** → `OLLAMA_BASE_URL` (masalan `http://sizning-server:11434`), `OLLAMA_MODEL`.

Hech biri sozlanmasa: AI tugmalari o'chib turadi, testlar va qolgan hammasi ishlaydi.
Har foydalanuvchiga soatiga `AI_RATE_PER_HOUR` (default 20) so'rov cheklovi bor.
