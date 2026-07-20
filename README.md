# מערכת ניתוח שוק — זהב · כסף · ביטקוין

דשבורד ווב עם 5 סוכנים שעובדים על שלושה נכסים (זהב/XAUUSD, כסף/XAGUSD, ביטקוין/BTCUSD):

1. **ויזואליזציה** — גרף מרובה טווחי-זמן בו-זמנית (15 דק / שעה / 4 שעות / יומי / שבועי).
2. **עונתיות** — דפוסים חוזרים לפי חודש/יום בשבוע, מחושב מהיסטוריית מחירים יומית.
3. **איזורים חשובים** — זיהוי תמיכה/התנגדות אוטומטי (pivot clustering).
4. **חדשות** — RSS + Groq (LLM), פיד חי בדשבורד (לא טלגרם).
5. **מוסדי** — COT Report (CFTC, ציבורי) + Smart Money Concepts (מבנה מחיר), מנוסח ע"י Groq.

המערכת רצה כתהליך (container) יחיד — ה-backend (FastAPI) מגיש גם את ה-API וגם את
הדשבורד הסטטי בעצמו, כדי שיהיה קל לפרוס אותה על פלטפורמת ענן חינמית בלי VPS.

הדשבורד הוא גם **PWA** — אחרי שהמערכת פרוסה ב-HTTPS, פתח את הכתובת בנייד:
ב-Android/Chrome תופיע אפשרות "התקן אפליקציה" (או תפריט ⋮ → "הוסף למסך הבית");
ב-iPhone/Safari: כפתור שיתוף → "הוסף למסך הבית". יופיע אייקון עצמאי שנפתח כמו אפליקציה,
בלי סרגל הכתובת של הדפדפן.

## ⚠️ שני מפתחות חינמיים שצריך כדי שהמערכת "תעבוד באמת"

**1. LLM — Groq (לא Gemini).** בדקנו כמה מפתחות Gemini קיימים (כולל דרך Google AI Studio)
וכולם החזירו `429 RESOURCE_EXHAUSTED ... limit: 0` — גוגל דורש היום הגדרת חיוב (גם אם
בפועל לא מחייבים) כדי לשחרר בכלל את המכסה החינמית של Gemini בחלק מהחשבונות. במקום זה
המערכת משתמשת ב-**Groq** — חינמי לגמרי, בלי כרטיס אשראי, הרשמה מיידית:
https://console.groq.com/keys — תשים את המפתח ב-`GROQ_API_KEY` ב-`.env`. בלי זה, סוכן
החדשות וסוכן המוסדי לא יפיקו ניתוח.

**2. זהב/כסף דורשים מפתח Twelve Data (חינמי).** בדקתי — Yahoo Finance חסום (429) מכל
סביבת ענן/VPS טיפוסית, אז הוא כבר לא המקור העיקרי. המקור העיקרי עכשיו הוא
**Twelve Data**: היכנס ל-https://twelvedata.com/pricing , הירשם (בלי כרטיס אשראי,
לוקח כ-10 שניות), ותשים את המפתח ב-`TWELVE_DATA_API_KEY` ב-`.env`. בלי זה, זהב וכסף
פשוט יתחילו ריקים ויצטברו בהדרגה רק מה-webhook החי של TradingView. ביטקוין לא מושפע —
נמשך מ-CoinGecko (בדקתי, עובד מצוין, לא דורש מפתח).

## הרצה מקומית

```bash
cd market_system/backend
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # venv/bin/pip בלינוקס/מק
cp .env.example .env   # ומלא GROQ_API_KEY + TWELVE_DATA_API_KEY + TRADINGVIEW_WEBHOOK_SECRET
./venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

פתח http://localhost:8000 — הדשבורד וה-API רצים על אותו פורט, אין צורך בשרת נוסף.

## פריסה לענן — בלי VPS (Railway / Render / Fly.io)

הכל בנוי סביב `Dockerfile` יחיד בשורש `market_system/`. בכל אחת מהפלטפורמות האלה:

1. חבר את הריפו (או השתמש ב-CLI של הפלטפורמה) וצור שירות חדש מסוג "Docker" / "Web Service".
2. הגדר את **Root Directory** (או "Source Directory") ל-`market_system` — כך הפלטפורמה
   תמצא את ה-`Dockerfile` ואת שתי התיקיות (`backend`, `frontend`) שהוא צריך.
3. הגדר את משתני הסביבה מתוך `backend/.env.example` (בממשק הפלטפורמה, לא בקובץ .env).
4. הפלטפורמה תיתן לך כתובת ציבורית עם HTTPS אוטומטי (למשל `xxx.up.railway.app`) —
   זו הכתובת שתשים ב-Webhook URL של TradingView (`https://xxx.up.railway.app/webhook/tradingview`)
   ותפתח בדפדפן לדשבורד עצמו.

**הערה חשובה על "השירות נרדם":** בחלק מהפלטפורמות (בעיקר Render בתוכנית החינמית)
שירות שלא קיבל תנועה כמה דקות "נרדם" ומתעורר רק כשמגיעה בקשה, עם עיכוב קר של כ-30-60
שניות. זה בעייתי במיוחד ל-webhook (אם TradingView שולח נר בדיוק כשהשירות ישן, יכול
להיווצר timeout ולפספס את הנתון). Railway ו-Fly.io בדרך כלל פחות אגרסיביים בזה, אבל
מדיניות התוכניות החינמיות משתנה — כדאי לבדוק את זה בפועל אחרי הפריסה (שלח webhook
ידני עם `curl` אחרי כמה דקות של חוסר פעילות ובדוק שהוא מגיע).

## חיבור TradingView (מקור המחירים)

ראה `pine/market_system_webhook.pine` — הוראות מלאות בראש הקובץ. בקצרה:

1. פתח את הגרף של הנכס (למשל OANDA:XAUUSD) על טווח הזמן שאתה רוצה שיהיה חי.
2. הוסף את האינדיקטור מה-Pine Editor, קבע `Internal symbol key` (XAUUSD/XAGUSD/BTCUSD)
   ו-`Webhook Secret` (חייב להיות זהה ל-`TRADINGVIEW_WEBHOOK_SECRET`).
3. צור Alert על האינדיקטור → Webhook URL = הכתובת הציבורית שקיבלת מהפלטפורמה + `/webhook/tradingview`.
4. חזור על זה לכל נכס ולכל טווח זמן שאתה רוצה חי (15 דק / שעה / 4 שעות / יומי / שבועי).

**שים לב:** webhook alerts ב-TradingView דורשים תוכנית בתשלום (Essential ומעלה) — לא זמין
בתוכנית החינמית של TradingView עצמו (זה נפרד מהפלטפורמה שמריצה את השרת).

## COT ו-Backfill

לא דורשים כלום ממך מעבר למפתח Twelve Data — `cot.py` מושך את דוח ה-CFTC הציבורי
אוטומטית (שבועי), ו-`backfill.py` ממלא היסטוריה (Twelve Data + yfinance לזהב/כסף,
CoinGecko לביטקוין) ברגע הראשון שהשרת עולה + כל כמה שעות.

## אם בעתיד יהיה לך VPS

`docker-compose.yml` + `Caddyfile` בשורש הפרויקט מוכנים לתרחיש הזה (Caddy מטפל
בדומיין + HTTPS אוטומטי מול ה-backend). באותו VPS: `docker compose up -d --build`.
לא נדרש היום — זה path חלופי בלבד.

## מבנה הפרויקט

```
market_system/
├── Dockerfile              # בונה backend+frontend יחד, ל-Railway/Render/Fly/VPS
├── docker-compose.yml, Caddyfile   # אופציונלי, רק לתרחיש VPS עם דומיין
├── backend/app/
│   ├── main.py             # FastAPI, endpoints, SSE, בוטסטראפ, ומגיש גם את ה-frontend
│   ├── scheduler.py         # APScheduler — מריץ את כל הסוכנים בלולאה
│   ├── webhooks.py           # קליטת נתונים חיים מ-TradingView
│   ├── db.py                 # SQLite
│   ├── ingestion/              # backfill (Twelve Data/yfinance/CoinGecko), cot.py, news_fetcher.py
│   └── agents/                  # news_agent, zones_agent, seasonality_agent, institutional_agent
├── frontend/                      # דשבורד סטטי (HTML/CSS/JS + lightweight-charts)
└── pine/market_system_webhook.pine
```

## Endpoints עיקריים

- `GET /api/symbols`, `/api/candles/{symbol}/{timeframe}`, `/api/zones/{symbol}/{timeframe}`
- `GET /api/seasonality/{symbol}/{month|weekday}`, `/api/cot/{symbol}`, `/api/institutional/{symbol}`
- `GET /api/news`, `GET /stream/news` (SSE — הפיד החי)
- `POST /webhook/tradingview` (התוודעות: `secret` בגוף הבקשה)
- `POST /api/admin/run/{news|zones|seasonality|institutional|backfill}` — הרצה ידנית לבדיקות;
  מושבת כברירת מחדל, דורש header `x-admin-token` שתואם ל-`ADMIN_TOKEN` ב-`.env`.
