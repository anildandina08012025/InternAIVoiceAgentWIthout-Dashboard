# EasyEducation AI Voice Agent — Priya
### Built with LiveKit (Self-Hosted) + VoBiz SIP + Sarvam AI + Groq + Google Sheets

Priya is an AI voice sales agent for Easy Education. She answers inbound calls, makes outbound calls, speaks in 4 Indian languages, captures leads, and logs everything to Google Sheets — all automatically.

---

## What Priya Can Do

| Feature | Description |
|---|---|
| **Inbound Calls** | Answers calls on your VoBiz number automatically |
| **Outbound Calls** | Calls numbers added to Google Sheet within 1-2 mins |
| **4 Languages** | English, Hindi, Telugu, Kannada — auto-detects from caller's speech |
| **Language Lock** | Stays in the detected language throughout the call |
| **Lead Capture** | Extracts caller Name, Grade, Interest using AI at call end |
| **Topic-Based Calls** | Specify a topic + language in the sheet — Priya talks about it |
| **Google Sheets CRM** | Logs every call to Outbound / Inbound / Leads tabs |
| **Indian Timezone** | All logs in IST |

---

## Architecture

### Inbound Call Flow
```
Caller dials +918065481599
  → VoBiz SIP Trunk
    → EC2 Public IP:5060 (livekit-sip Docker)
      → LiveKit Server (localhost:7880)
        → agent_inbound_easyedu.py answers
          → Sarvam STT (hears caller)
          → Groq LLM (thinks and replies)
          → Sarvam TTS Priya voice (speaks)
          → At call end → logs to Google Sheets (Inbound + Leads)
```

### Outbound Call Flow
```
Google Sheet → Outbound tab → add Phone + Topic + Language
  → Apps Script checkOutbound() runs every 1 min
    → POST to EC2 call_webhook.py (port 8090)
      → LiveKit dispatch → agent_outbound_easyedu.py
        → Calls number via VoBiz SIP
          → Priya speaks about the topic in specified language
```

---

## Tech Stack

| Layer | Technology | Details |
|---|---|---|
| **Phone / SIP** | VoBiz | SIP trunking, Indian phone numbers |
| **Voice Server** | LiveKit (self-hosted) | Real-time audio, room management |
| **SIP Bridge** | livekit-sip (Docker) | Connects SIP calls to LiveKit |
| **STT** | Sarvam saarika:v2.5 | Indian language speech recognition |
| **TTS** | Sarvam bulbul:v3 (Priya voice) | Natural Indian language speech |
| **LLM** | Groq llama-3.3-70b-versatile | Fast AI brain (~200ms response) |
| **VAD** | Silero | Detects when caller is speaking |
| **Webhook Server** | Flask (port 8090) | Receives triggers from Google Sheets |
| **CRM** | Google Sheets + Apps Script | Logs calls, leads, triggers outbound |
| **Server** | AWS EC2 t2.micro, Ubuntu 22.04, Mumbai | Hosts everything |

---

## Project Files

```
livekit-project/ (on EC2) / Vobiz+Livekit(selfhost)/ (local)
│
├── agent_inbound_easyedu.py   ← Inbound AI voice agent (Priya)
├── agent_outbound_easyedu.py  ← Outbound AI voice agent (Priya)
├── call_webhook.py            ← Flask server — receives Google Sheets triggers
├── google_apps_script.js      ← Google Apps Script (paste in Apps Script editor)
│
├── docker-compose.yml         ← Runs Redis + LiveKit + SIP bridge (DO NOT EDIT)
├── livekit.yaml               ← LiveKit server config (DO NOT EDIT)
├── sip.yaml                   ← SIP bridge config (DO NOT EDIT)
├── setup_dispatch.py          ← Creates SIP trunk + dispatch rule (DO NOT EDIT)
├── start.sh                   ← One-command startup script (DO NOT EDIT)
│
├── requirements.txt           ← Python dependencies
└── .env                       ← API keys — NEVER share or commit to Git!
```

---

## Services & API Keys Needed

| Service | Purpose | Cost |
|---|---|---|
| **VoBiz** | Phone numbers + SIP trunking | Paid (per min) |
| **AWS EC2** | Server to run everything | ~₹1/hr (t2.micro) |
| **Sarvam AI** | Indian STT + TTS | Free credits available |
| **Groq** | LLM (AI brain) | Free tier available |
| **LiveKit** | Self-hosted, no cost | Free (EC2 cost only) |
| **Google Sheets** | CRM for calls + leads | Free |

---

## .env File (on EC2 only — never share)

```env
# LiveKit (self-hosted)
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# Groq
GROQ_API_KEY=your_groq_api_key_here

# Sarvam AI
SARVAM_API_KEY=your_sarvam_api_key_here

# VoBiz SIP
OUTBOUND_TRUNK_ID=ST_xxxxxxxxxxxxxxxxx

# Webhook
WEBHOOK_SECRET=easyedu-secret-2026

# Google Sheets (Web App URL from Apps Script deploy)
SHEETS_WEBHOOK_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
```

---

## One-Time Setup (Fresh EC2 Instance)

### Step 1 — Launch EC2
- Type: **t2.micro**, Ubuntu 22.04, Region: **ap-south-1 (Mumbai)**
- Key pair: create and download `.pem` file
- Security Group — open these ports:

| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | Your IP | SSH |
| 7880 | TCP | Anywhere | LiveKit |
| 7881 | TCP | Anywhere | LiveKit WebRTC |
| 7882 | UDP | Anywhere | LiveKit WebRTC |
| 5060 | TCP+UDP | Anywhere | SIP |
| 8090 | TCP | Anywhere | Webhook (Google Sheets) |
| 50000-60000 | UDP | Anywhere | RTP media |

### Step 2 — SSH into EC2
```bash
ssh -o StrictHostKeyChecking=no -i ~/Downloads/your-key.pem ubuntu@YOUR_EC2_IP
```

### Step 3 — Install dependencies
```bash
# Add swap (required for t2.micro — only 1GB RAM)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Install Docker + Python
sudo apt update && sudo apt install -y docker.io docker-compose python3-pip
sudo usermod -aG docker ubuntu
newgrp docker

# Install Python packages
pip3 install livekit-agents>=1.5.0 livekit-api livekit-plugins-groq \
  livekit-plugins-sarvam livekit-plugins-silero livekit-plugins-openai \
  python-dotenv flask langdetect requests
```

### Step 4 — Fix Sarvam TTS bug (IMPORTANT — must do after every reinstall)
```bash
sudo sed -i 's/mime_type="audio\/wav"/mime_type="audio\/mpeg"/g' \
  ~/.local/lib/python3.10/site-packages/livekit/plugins/sarvam/tts.py
```

### Step 5 — Create project folder and upload files
```bash
mkdir ~/livekit-project
```

From your local machine (Windows PowerShell):
```powershell
scp -o StrictHostKeyChecking=no -i "C:\path\to\key.pem" `
  "C:\Users\keert\OneDrive\Desktop\Vobiz+Livekit(selfhost)\*" `
  ubuntu@YOUR_EC2_IP:~/livekit-project/
```

### Step 6 — Create .env on EC2
```bash
nano ~/livekit-project/.env
```
Paste your API keys (see .env template above).

### Step 7 — Start everything
```bash
cd ~/livekit-project
sudo docker-compose up -d
sleep 10
python3 setup_dispatch.py
nohup python3 agent_inbound_easyedu.py start > inbound.log 2>&1 &
nohup python3 agent_outbound_easyedu.py start > outbound.log 2>&1 &
nohup python3 call_webhook.py > webhook.log 2>&1 &
```

### Step 8 — Update VoBiz
- VoBiz Console → SIP Trunk → Inbound → Edit → set Primary URI to `YOUR_EC2_IP`

### Step 9 — Set up Google Sheets
See **Google Sheets Setup** section below.

---

## Every Time: Start After EC2 Restart

EC2 IP changes every time you stop/start. Do these 3 things:

**1. Update VoBiz:**
- VoBiz → Inbound Trunk → Primary URI → `NEW_IP`

**2. Update Apps Script:**
- Apps Script → ⚙️ Settings → Script Properties
- `EC2_WEBHOOK_URL` → `http://NEW_IP:8090/trigger-call`

**3. SSH and start agents:**
```bash
ssh -i key.pem ubuntu@NEW_IP
cd ~/livekit-project
sudo docker-compose up -d
sleep 5
nohup python3 agent_inbound_easyedu.py start > inbound.log 2>&1 &
nohup python3 agent_outbound_easyedu.py start > outbound.log 2>&1 &
nohup python3 call_webhook.py > webhook.log 2>&1 &
```

---

## Google Sheets Setup (One Time)

### Step 1 — Create Google Sheet
- Create a new Google Sheet
- Rename tabs: **Outbound**, **Inbound**, **Leads**
- Copy the Spreadsheet ID from the URL

### Step 2 — Set up Apps Script
- Extensions → Apps Script
- Delete all existing code
- Paste content from `google_apps_script.js`
- Save

### Step 3 — Set Script Properties
- ⚙️ Settings → Script Properties → Add:

| Property | Value |
|---|---|
| `SPREADSHEET_ID` | Your sheet ID from URL |
| `EC2_WEBHOOK_URL` | `http://YOUR_EC2_IP:8090/trigger-call` |
| `WEBHOOK_SECRET` | `easyedu-secret-2026` |

### Step 4 — Run setupSheets()
- Select `setupSheets` in dropdown → ▶️ Run
- Allow permissions when asked

### Step 5 — Deploy as Web App
- Deploy → New Deployment → Web App
- Execute as: **Me**, Who has access: **Anyone**
- Copy the Web App URL

### Step 6 — Add Web App URL to EC2 .env
```bash
echo "SHEETS_WEBHOOK_URL=https://script.google.com/macros/s/YOUR_ID/exec" >> ~/livekit-project/.env
```

### Step 7 — Add Time Trigger
- Apps Script → ⏰ Triggers → Add Trigger
- Function: `checkOutbound`, Time-driven, Every minute

---

## How to Use

### Outbound Call with Topic
Add a row to the **Outbound** tab:

| Phone Number | Topic | Language | Status | Called At |
|---|---|---|---|---|
| +918762012312 | Explain Grade 10 Science 3D lessons | Hindi | | |
| +917013026413 | Tell about board exam preparation | Telugu | | |

Wait 1-2 minutes → Status changes to `Called ✓` → Priya calls!

### Inbound Call
- Call **+918065481599**
- Priya answers, detects your language, speaks accordingly
- After call → check **Inbound** and **Leads** tabs for logged data

---

## Check Status

```bash
# Are all 3 processes running?
ps aux | grep -E "agent_inbound|agent_outbound|call_webhook" | grep -v grep

# Check inbound logs
tail -30 ~/livekit-project/inbound.log

# Check outbound logs
tail -30 ~/livekit-project/outbound.log

# Check webhook logs
tail -20 ~/livekit-project/webhook.log

# Docker containers
sudo docker ps
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| Agent doesn't answer | Agent not running | Run agents with nohup commands above |
| Agent answers but silent | Sarvam mime_type bug | Re-apply the `sed` patch in Step 4 |
| Outbound call not triggered | EC2 IP changed | Update Apps Script `EC2_WEBHOOK_URL` |
| SIP trunk not found (404) | Redis wiped on docker restart | Run `setup_dispatch.py` again |
| `python: command not found` | Use `python3` on Ubuntu | Replace `python` with `python3` |
| `docker-compose: permission denied` | Need sudo | Use `sudo docker-compose` |
| Language shows English always | Event name wrong | Already fixed: uses `user_input_transcribed` |

---

## Important Notes

1. **Sarvam TTS bug**: Plugin hardcodes `mime_type="audio/wav"` but API returns `audio/mpeg` → silent calls. Must patch after every reinstall.

2. **Redis wipes on docker restart**: SIP trunk + dispatch rule lost. Run `setup_dispatch.py` again.

3. **EC2 IP changes on every stop/start**: Update VoBiz + Apps Script every time.

4. **t2.micro RAM**: Only 1GB + 1GB swap. Groq is the right LLM — do not use heavier models.

5. **Never commit .env to Git**: Contains API keys. Already in `.gitignore`.

---

*Last updated: April 2026 | Project: EasyEducation AI Voice Agent | Persona: Priya*
