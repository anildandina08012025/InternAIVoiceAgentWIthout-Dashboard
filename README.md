# Aivoro Hospital AI Assistant — Priya

## S-R-M Travels outbound feedback calls

Outbound calls with no `call_mode` and no `appointment_at` use Priya as the S-R-M Elite Travels AI receptionist. She asks about the bus journey and an honest rating, politely invites a five-star rating in the app when appropriate, and listens to complaints. Existing appointment calls can use `call_mode: "appointment-reminder"`; an `appointment_at` also selects the appointment flow. The inbound agent is unchanged.

Deploy the updated `google_apps_script.js` as the existing Sheets web app and update its deployment. Set `SHEETS_WEBHOOK_URL` and `WEBHOOK_SECRET` in the agent environment, and set the same `WEBHOOK_SECRET` plus `SPREADSHEET_ID` in Apps Script properties. Restart the outbound worker and webhook. The assistant saves feedback to the automatically created **SRM Feedback** tab and confirms the save only after the spreadsheet responds successfully. The team must review that tab; this does not send a separate notification or automatically forward complaints. If saving fails, the assistant is instructed to say so.

Add a customer's phone number to the existing **Outbound** tab, or send `call_mode: "srm-travels-feedback"` to `/trigger-call`. Travel calls start in Kannada and support Kannada, Telugu, and English. A successful dispatch does not prove the call was answered. Test the complete flow with an authorized number before use.

To use Google Gemini TTS for Kannada, set `GOOGLE_TTS_API_KEY` and `KANNADA_TTS_PROVIDER=google` in `.env`, then restart the outbound worker. `GOOGLE_GEMINI_TTS_VOICE` defaults to `Kore`; Telugu and English continue to use Sarvam. If no API key is present, the Google Cloud TTS integration instead uses service-account credentials from `GOOGLE_TTS_CREDENTIALS_JSON`, Application Default Credentials, or `GOOGLE_APPLICATION_CREDENTIALS`. With `KANNADA_TTS_PROVIDER=sarvam`, Kannada also uses Sarvam.

Priya answers hospital service enquiries, collects appointment requests, and makes reminder calls in English, Hindi, Telugu, and Kannada.

Both voice agents and inbound lead extraction use `openai/gpt-oss-120b` through OpenRouter, restricted to Cerebras. Add `OPENROUTER_API_KEY` to `.env` and restart both workers. The key must be from OpenRouter; an OpenAI API key will not work. If Cerebras is unavailable, requests fail instead of falling back to another provider.

## Hospital appointment workflow

- Deploy the updated `google_apps_script.js` as your Google Sheets web app and run `setupSheets()` to create the **Appointments** tab. Update the existing web app deployment so the agents use this version.
- Set the same `WEBHOOK_SECRET` in the Python `.env` and Apps Script properties, alongside `SHEETS_WEBHOOK_URL`, `SPREADSHEET_ID`, and `EC2_WEBHOOK_URL`.
- The inbound agent collects patient name, phone, department, preferred date/time, and reminder consent. After patient confirmation it saves a **Pending** request and returns a reference. Reception must verify the slot and change **Status** to **Confirmed**; this integration does not check a doctor calendar.
- Add an Apps Script time trigger for `checkReminders`, every minute. It dispatches calls one hour before confirmed appointments with reminder consent. Reception can change **Reminder At**. Set spreadsheet timezone to Asia/Kolkata.
- **Dispatched** means the calling job was accepted, not that the patient answered. Review failed or uncertain jobs before clearing **Reminder Status** to retry. Cancelled appointments and appointments without consent are skipped.
- Restart both Python workers and the webhook after updating files. Existing worker names and filenames are retained for compatibility.

Aivoro Hospital is described as providing comprehensive treatment. Actual department lists, doctors, fees, address, and opening hours must be supplied by the hospital; the assistant asks staff to confirm unknown details. No live calls or remote deployments are performed by this local change.

---

## Existing infrastructure setup reference

## Architecture

### Inbound Call Flow
```
Caller dials +918065481599
  → VoBiz SIP Trunk
    → EC2 Public IP:5060 (livekit-sip Docker)
      → LiveKit Server (localhost:7880)
        → agent_inbound_easyedu.py answers
          → Sarvam STT (hears caller)
          → OpenRouter / Cerebras LLM (thinks and replies)
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
| **LLM** | OpenRouter / Cerebras openai/gpt-oss-120b | AI conversation and lead extraction |
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
| **OpenRouter** | LLM access through Cerebras | Usage-based pricing |
| **LiveKit** | Self-hosted, no cost | Free (EC2 cost only) |
| **Google Sheets** | CRM for calls + leads | Free |

---

## .env File (on EC2 only — never share)

```env
# LiveKit (self-hosted)
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# OpenRouter
OPENROUTER_API_KEY=your_openrouter_api_key_here

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

## LiveKit Cloud + VoBiz Inbound SIP Setup

Use this section when running the agents from a laptop or with LiveKit Cloud, instead of forwarding VoBiz to a self-hosted EC2 SIP server.

### Where to find the LiveKit SIP host

In LiveKit Cloud:

1. Open your LiveKit Cloud project.
2. Go to **Project settings**.
3. Open **General**.
4. Copy the value shown as **SIP URI**.

Example:

```text
sip:3bdgw8gzp6t.sip.livekit.cloud
```

For VoBiz, remove the `sip:` prefix. Enter only:

```text
3bdgw8gzp6t.sip.livekit.cloud
```

Important: the **Project URL** and **SIP URI** are not the same.

```text
Project URL: test-hospital-hw9cmyt9.livekit.cloud
SIP URI:     3bdgw8gzp6t.sip.livekit.cloud
```

Do not guess the SIP host from `LIVEKIT_URL`. Always copy it from LiveKit Cloud **Project settings -> General -> SIP URI**.

### VoBiz Origination URI

In VoBiz:

1. Go to **SIP Trunk -> Inbound Trunks -> Origination URI**.
2. Create a URI.
3. Enter the LiveKit SIP host without `sip:`.
4. Use **UDP** first.

Recommended first test:

```text
Name: LiveKitCloud
URI: 3bdgw8gzp6t.sip.livekit.cloud
Transport: UDP
```

If VoBiz shows a host-port warning, click **Save anyway**. LiveKit Cloud SIP URIs can work without manually adding `:5060`.

If the no-port URI fails, test this second:

```text
Name: LiveKitCloud5060
URI: 3bdgw8gzp6t.sip.livekit.cloud:5060
Transport: UDP
```

Then go to **SIP Trunk -> Inbound Trunks -> Trunks -> Edit inbound trunk** and set **Primary URI** to the working LiveKit URI.

### LiveKit inbound trunk requirements

The LiveKit inbound trunk must match the VoBiz number and allow VoBiz SIP traffic.

For testing, use:

```text
Phone numbers:
+918065481599
918065481599
08065481599
8065481599

Allowed addresses:
0.0.0.0/0
```

The dispatch rule must point to the same inbound trunk and must dispatch the correct agent name:

```text
Agent name: inbound-assistant
Room prefix: inbound-
```

The Python inbound worker must also use the same agent name:

```python
agent_name="inbound-assistant"
```

### Issue we faced and final resolution

The inbound call reached VoBiz, but LiveKit did not receive any room/job. VoBiz call logs showed:

```text
Direction: Inbound
Status: Not answered
Bill Sec: 0
Hangup Cause Code: 4000
Terminated To: inbound_carrier
```

The first incorrect VoBiz URI was based on the LiveKit Project URL:

```text
test-hospital-hw9cmyt9.sip.livekit.cloud
```

The correct SIP URI was found in LiveKit Cloud settings:

```text
sip:3bdgw8gzp6t.sip.livekit.cloud
```

The VoBiz URI should therefore be:

```text
3bdgw8gzp6t.sip.livekit.cloud
```

Final working result: inbound calls started working after using the correct LiveKit Cloud SIP URI in VoBiz and changing the first AI greeting to direct TTS with `session.say()` instead of waiting for `session.generate_reply()`. This reduced the initial answer delay enough for PSTN inbound calls.

Final working configuration:

```text
VoBiz number: +918065481599
VoBiz inbound trunk: AIHospitalInboun
VoBiz Primary URI: 3bdgw8gzp6t.sip.livekit.cloud or 3bdgw8gzp6t.sip.livekit.cloud:5060
Transport: UDP
LiveKit inbound agent name: inbound-assistant
Inbound worker file: agent_inbound_easyedu.py
First greeting method: session.say()
```

If calls again say "not reachable" or LiveKit does not receive the call, collect these values from VoBiz call logs and send them to VoBiz support:

```text
Direction: Inbound
Destination country: India
Destination number: +918065481599
Timestamp with timezone
VoBiz Call ID
SIP Call ID
Trunk ID
Hangup Cause Code
Terminated To
```

Ask VoBiz support to confirm the exact SIP INVITE destination and the SIP response received from LiveKit.

---
## Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| Agent doesn't answer | Agent not running | Run agents with nohup commands above |
| Agent answers but silent | Sarvam mime_type bug | Re-apply the `sed` patch in Step 4 |
| Outbound call not triggered | EC2 IP changed | Update Apps Script `EC2_WEBHOOK_URL` |
| SIP trunk not found (404) | Redis wiped on docker restart | Run `setup_dispatch.py` again |
| Inbound call says not reachable | VoBiz URI is wrong or not reaching LiveKit SIP | Use LiveKit Cloud **SIP URI**, not Project URL; remove `sip:` in VoBiz |
| Inbound call reaches VoBiz but LiveKit gets no room/job | VoBiz-to-LiveKit SIP forwarding issue | Check VoBiz Primary URI, UDP transport, LiveKit allowed addresses, and dispatch rule |
| Inbound call reaches LiveKit but caller hears not reachable or disconnects fast | First greeting is too slow | Use direct `session.say()` for the opening greeting instead of `session.generate_reply()` |
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

*Last updated: August 2026 | Project: AI Hospital Voice Agent | Persona: Priya*



