# SKILL SHEET — EasyEducation AI Voice Agent (Priya)

> **Project:** AI Voice Sales Agent for Easy Education  
> **Persona:** Priya — friendly multilingual AI calling agent  
> **Built by:** Aivoro Team  
> **Stack:** LiveKit + VoBiz + Sarvam AI + Groq + Google Sheets  

---

## What This Project Does

Priya is a fully automated AI voice agent that:
- **Answers inbound calls** — caller dials VoBiz number → Priya picks up, detects language, speaks naturally
- **Makes outbound calls** — add a phone number + topic + language to Google Sheets → Priya calls within 1-2 mins
- **Speaks 4 Indian languages** — English, Hindi, Telugu, Kannada (auto-detected from caller's speech)
- **Captures leads** — extracts caller name, grade, interest level using AI after every call
- **Logs everything** — every call logged to Google Sheets (Inbound + Leads tabs)

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Phone / SIP** | VoBiz | Indian phone numbers, SIP trunking |
| **Voice Server** | LiveKit (self-hosted on EC2) | Real-time audio, free self-hosted |
| **SIP Bridge** | livekit-sip (Docker) | Connects SIP calls to LiveKit |
| **STT** | Sarvam saarika:v2.5 | Best Indian language speech-to-text |
| **TTS** | Sarvam bulbul:v3, Priya voice | Natural Indian voice output |
| **LLM** | Groq llama-3.3-70b-versatile | Fast (~200ms), multilingual AI |
| **VAD** | Silero | Detects when caller is speaking |
| **Webhook** | Flask (port 8090) | Receives Google Sheets triggers |
| **CRM** | Google Sheets + Apps Script | No-code CRM for leads and calls |
| **Server** | AWS EC2 t2.micro, Ubuntu 22.04, Mumbai | Affordable, always-on server |

---

## Features Built

### 1. Inbound Call Handling
- Priya answers all calls on +918065481599
- Greets in English first, then switches to caller's language
- 2-3 sentence concise responses (optimized for voice)

### 2. Multilingual Support
- **4 languages**: English, Hindi, Telugu, Kannada
- **Unicode-based detection** (reliable for Indian scripts)
- **Language lock**: injects system message into Groq context to prevent language mixing
- Malayalam script auto-mapped to Kannada (Sarvam STT quirk)

### 3. Outbound Calls via Google Sheets
- Add phone number to Outbound tab → Priya calls within 1-2 mins
- Apps Script polls sheet every 1 minute
- Status updates automatically: `Calling...` → `Called ✓`

### 4. Topic-Based Outbound Calls
- Specify Topic + Language in the Outbound sheet
- Priya calls and talks specifically about that topic in that language
- Example: `"Explain Grade 10 Science 3D lessons"` + `"Hindi"`

### 5. Lead Capture
- Priya naturally asks for caller's name and grade during conversation
- At call end → Groq extracts Name, Grade, Interest (High/Medium/Low)
- Logs to **Leads tab** in Google Sheets automatically

### 6. Call Logging
- Every inbound call logged: Caller Number, Language, Date, Time, Duration
- All times in IST (Indian Standard Time)

---

## System Architecture

```
INBOUND:
  Caller dials VoBiz number (+918065481599)
    → VoBiz SIP Trunk → EC2:5060 (livekit-sip Docker)
      → LiveKit Server (localhost:7880)
        → agent_inbound_easyedu.py
          → Sarvam STT → Groq LLM → Sarvam TTS (Priya)
          → Call ends → Groq extracts lead → POST to Google Sheets

OUTBOUND:
  Google Sheet (Outbound tab) → Phone + Topic + Language added
    → Apps Script checkOutbound() every 1 min
      → POST http://EC2_IP:8090/trigger-call (call_webhook.py)
        → LiveKit agent dispatch
          → agent_outbound_easyedu.py → VoBiz SIP → Phone rings
            → Priya speaks about the topic in specified language
```

---

## Project Files

```
livekit-project/
├── agent_inbound_easyedu.py    ← Inbound agent — handles all inbound calls
├── agent_outbound_easyedu.py   ← Outbound agent — makes outbound calls
├── call_webhook.py             ← Flask webhook — receives Sheets trigger
├── google_apps_script.js       ← Paste in Google Apps Script editor
├── docker-compose.yml          ← Docker: Redis + LiveKit + SIP bridge
├── livekit.yaml                ← LiveKit server config
├── sip.yaml                    ← SIP bridge config
├── setup_dispatch.py           ← Creates SIP dispatch rules in LiveKit
├── start.sh                    ← One-command startup
├── requirements.txt            ← Python dependencies
└── .env                        ← API keys (NEVER commit to Git)
```

---

## Google Sheets Structure

### Outbound Tab
| Phone Number | Topic | Language | Status | Called At |
|---|---|---|---|---|
| +918762012312 | Explain Grade 10 Maths | Hindi | Called ✓ | 09-04-2026 14:30 |

### Inbound Tab
| Caller Number | Language | Call Date | Call Time | Duration (mins) |
|---|---|---|---|---|
| 917013026413 | Telugu | 2026-04-09 | 14:22:37 | 1.59 |

### Leads Tab
| Phone | Name | Grade | Language | Interest | Call Date | Call Time |
|---|---|---|---|---|---|---|
| 917013026413 | Tirthana | Class 7 | Telugu | High | 2026-04-09 | 14:22:37 |

---

## API Keys Required

| Service | Key Name in .env | Where to Get |
|---|---|---|
| Groq | `GROQ_API_KEY` | console.groq.com |
| Sarvam AI | `SARVAM_API_KEY` | app.sarvam.ai |
| LiveKit | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` | Self-hosted (use devkey/secret) |
| Google Sheets | Web App URL | Apps Script deploy |

---

## Known Bugs & Fixes

| Bug | Fix Applied |
|---|---|
| Sarvam TTS silent (no audio) | Patch `mime_type="audio/wav"` → `"audio/mpeg"` in plugin |
| Language stuck at English | Changed event from `user_speech_committed` → `user_input_transcribed` |
| Language detection needs long speech | Lowered threshold from `>= 10` to `>= 3` chars |
| Groq mixes languages | Language lock system message injected into chat context |
| SIP trunk lost after docker restart | Redis wipes on restart → run `setup_dispatch.py` again |
| EC2 IP changes after restart | Update VoBiz + Apps Script Script Properties each time |

---

## Cost Estimate (Monthly)

| Service | Cost |
|---|---|
| AWS EC2 t2.micro (24/7) | ~₹700/month |
| VoBiz (inbound number) | ₹500/month + per-min charges |
| Sarvam AI | Pay per use (free credits available) |
| Groq | Free tier (very generous) |
| **Total** | **~₹1,200-1,500/month** |

> Stop EC2 when not in use to save costs — restart takes ~2 minutes.

---

## Future Features (Roadmap)

| Feature | Description |
|---|---|
| **Call Scheduling** | Caller says "call me tomorrow 5pm" → Priya auto-books |
| **Call Recording** | Save audio + transcripts to S3 |
| **Voice Routing** | "For admissions say 1, for support say 2" |
| **WhatsApp Follow-up** | Auto-send WhatsApp after call |
| **Tamil + Malayalam** | Add 2 more languages |
| **RAG Knowledge Base** | Upload PDFs → Priya answers from real content |
| **Dashboard** | Google Sheets formula dashboard for leads summary |

---

*Last updated: April 2026 | Built by Aivoro Team*
