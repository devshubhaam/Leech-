# 🤖 Telegram Leech Bot — Personal Single-User

A production-ready personal Telegram bot that downloads files from almost any
link and sends them back to you — optimized for Render.com free tier.

---

## 📁 Project Structure

```
leech_bot/
├── main.py                  # Entry point
├── config.py                # All config / env vars
├── requirements.txt
├── render.yaml              # Render deployment config
├── Procfile
├── build.sh                 # System deps installer for Render
├── .env.example             # Template — copy to .env locally
├── .gitignore
│
├── bot/
│   ├── __init__.py
│   ├── handlers.py          # /start /help /leech /cancel + message handler
│   ├── middleware.py        # Owner-only guard
│   └── queue.py             # Async task queue
│
├── downloader/
│   ├── __init__.py
│   ├── dispatcher.py        # Auto-detects link type → routes to correct DL
│   ├── aria2_dl.py          # Direct/CDN links via aria2c
│   ├── http_dl.py           # Fallback pure-aiohttp streamer
│   ├── ytdlp_dl.py          # YouTube/Vimeo/1000+ sites via yt-dlp
│   ├── mega_dl.py           # MEGA.nz links via megapy
│   └── torrent_dl.py        # Magnet/torrent via aria2c
│
└── utils/
    ├── __init__.py
    ├── cleanup.py           # Temp file deletion
    ├── filetools.py         # File splitting for >50MB files
    └── progress.py          # Progress bar / speed / ETA rendering
```

---

## ⚡ Tech Stack Choices Explained

| Choice | Why |
|---|---|
| **python-telegram-bot** | Cleaner async API than Pyrogram for bot-only use; no MTProto needed |
| **Polling (not webhook)** | Render free tier sleeps on inactivity — polling keeps the worker alive without needing a public HTTPS URL |
| **aria2c** | Multi-connection CDN downloads, magnet/torrent support, battle-tested |
| **yt-dlp** | 1000+ site support, actively maintained fork of youtube-dl |
| **megapy** | Actively maintained; works for public files without credentials |
| **/tmp for downloads** | Render free gives ~512 MB ephemeral disk; /tmp is always writable |

---

## 🚀 Step 1: Create Your Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Follow prompts → you get a **BOT_TOKEN** like `123456:ABCdef...`
4. Save it securely

---

## 🪪 Step 2: Get Your OWNER_ID

1. Open Telegram → search **@userinfobot**
2. Send `/start`
3. It replies with your **numeric user ID** (e.g. `987654321`)
4. Save it — this is your `OWNER_ID`

---

## 💻 Step 3: Run Locally First (Recommended)

### Prerequisites
```bash
# Ubuntu/Debian
sudo apt-get install aria2 ffmpeg python3 python3-pip

# macOS
brew install aria2 ffmpeg python3
```

### Setup
```bash
git clone <your-repo>
cd leech_bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install Python deps
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — fill in BOT_TOKEN and OWNER_ID
nano .env
```

### Run
```bash
# Load .env and start
export $(cat .env | xargs)
python main.py
```

Open Telegram → send `/start` to your bot. It should respond!

---

## ☁️ Step 4: Deploy to Render.com

### 4.1 Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/leech-bot.git
git push -u origin main
```

### 4.2 Create Render Service
1. Go to **https://render.com** → Sign in
2. Click **"New +"** → **"Background Worker"**
   - *(NOT Web Service — bots don't need HTTP)*
3. Connect your GitHub repo
4. Configure:
   - **Name:** `telegram-leech-bot`
   - **Branch:** `main`
   - **Build Command:**
     ```
     chmod +x build.sh && ./build.sh
     ```
   - **Start Command:**
     ```
     python main.py
     ```
   - **Instance Type:** Free

### 4.3 Add Environment Variables
In Render dashboard → **Environment** tab → add:

| Key | Value |
|---|---|
| `BOT_TOKEN` | Your token from BotFather |
| `OWNER_ID` | Your numeric Telegram ID |
| `DOWNLOAD_DIR` | `/tmp/leech_downloads` |
| `MAX_DOWNLOAD_SIZE` | `419430400` |
| `YTDLP_MAX_HEIGHT` | `720` |
| `MEGA_EMAIL` | *(optional)* your MEGA email |
| `MEGA_PASSWORD` | *(optional)* your MEGA password |

### 4.4 Deploy
Click **"Create Background Worker"** — Render will:
1. Clone your repo
2. Run `build.sh` (installs aria2, ffmpeg, Python deps)
3. Start `python main.py`

Watch the **Logs** tab — you should see:
```
Starting Leech Bot (polling mode) …
Owner ID : 987654321
Bot is running.
```

---

## 📱 How to Use the Bot

| Action | What to do |
|---|---|
| Download any file | `/leech https://example.com/file.zip` |
| Download video | `/leech https://youtu.be/xxxx` |
| Download MEGA | `/leech https://mega.nz/file/xxxxx` |
| Download torrent | `/leech magnet:?xt=urn:btih:...` |
| Just paste a URL | Send raw URL — bot auto-detects |
| Cancel current task | `/cancel` |
| Show help | `/help` |

---

## ⚠️ Render Free Tier Limitations (Honest)

| Limitation | Impact | Workaround |
|---|---|---|
| **512 MB ephemeral disk** | Can't download files >~400 MB reliably | Set `MAX_DOWNLOAD_SIZE=419430400` |
| **512 MB RAM** | Large yt-dlp merges may OOM | Use 720p cap (`YTDLP_MAX_HEIGHT=720`) |
| **No persistent disk** | Downloads lost on restart (expected) | Files are sent to Telegram before restart |
| **Worker may sleep** | Free workers sleep after ~15min idle | Use polling; wake on message arrival |
| **BitTorrent ports may be blocked** | Magnet links unreliable | Use direct/MEGA links instead |
| **No static IP** | Some CDNs may block | Usually not an issue |
| **750 hrs/month free** | ~31 days — essentially unlimited for a background worker | Fine for personal use |

---

## 📏 Telegram Bot API File Limits

| Limit | Value |
|---|---|
| Max upload via Bot API | **50 MB** per file |
| Files >50 MB | Auto-split into 49 MB parts |
| Max file parts | No hard limit |

> **Note:** With a local Telegram Bot API server you can upload up to 2 GB,
> but that requires running the server yourself. This bot uses the public API (50 MB limit).

---

## 🔒 Security Notes

- `OWNER_ID` check happens before ANY processing — all other users are silently ignored
- Bot token is NEVER in code — only environment variables
- No data is stored — files deleted immediately after upload
- No database, no logs with personal data

---

## 🐛 Troubleshooting

**Bot not responding:**
- Check Render logs for errors
- Verify `BOT_TOKEN` is correct
- Verify `OWNER_ID` matches your actual Telegram ID

**MEGA download failing:**
- Public files work without credentials
- Private files need `MEGA_EMAIL` + `MEGA_PASSWORD`
- MEGA rate-limits anonymous downloads

**yt-dlp fails for a site:**
- Update yt-dlp: `pip install -U yt-dlp`
- Some sites have bot protection (Cloudflare, etc.)

**File too large:**
- Bot will auto-split into 49 MB parts
- Very large files (>400 MB) may exhaust Render's disk — reduce `MAX_DOWNLOAD_SIZE`

**aria2c not found on Render:**
- Ensure `build.sh` ran successfully
- Check build logs in Render dashboard
