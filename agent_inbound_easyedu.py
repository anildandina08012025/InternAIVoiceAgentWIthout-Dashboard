"""
agent_inbound_easyedu.py
=========================
EasyEducation AI Voice Agent — Inbound Calls
- Persona: Priya from Easy Education
- Multilingual: Detects caller language, switches Sarvam TTS to match
- STT: Sarvam saarika:v2.5
- TTS: Sarvam bulbul:v3, speaker priya
- LLM: Groq llama-3.3-70b-versatile
"""

import logging
import os
import json
import asyncio
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import sarvam, silero
from livekit.plugins import groq

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("easyedu-agent")

SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL", "")
IST = timezone(timedelta(hours=5, minutes=30))

# ─────────────────────────────────────────────
# LANGUAGE MAPS
# ─────────────────────────────────────────────
LANG_TO_SARVAM = {
    "hi": "hi-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "en": "en-IN",
}
LANG_NAMES = {
    "hi-IN": "Hindi",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "en-IN": "English",
}

# Injected into chat context when language is detected — forces Groq to stay in that language
LANG_LOCK = {
    "hi-IN": "LANGUAGE LOCK ACTIVE: The caller is speaking Hindi. From this point forward, ALL your responses must be EXCLUSIVELY in Hindi (Devanagari script हिंदी). Do not use English or any other language. Every single word must be Hindi.",
    "te-IN": "LANGUAGE LOCK ACTIVE: The caller is speaking Telugu. From this point forward, ALL your responses must be EXCLUSIVELY in Telugu (తెలుగు script). Do not use English or any other language. Every single word must be Telugu.",
    "kn-IN": "LANGUAGE LOCK ACTIVE: The caller is speaking Kannada. From this point forward, ALL your responses must be EXCLUSIVELY in Kannada (ಕನ್ನಡ script). Do not use English or any other language. Every single word must be Kannada.",
    "en-IN": "Continue responding in English only.",
}

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are Priya, a friendly voice AI assistant for Easy Education — India's AI-powered ed-tech platform.

STRICT LANGUAGE RULE — You ONLY support these 4 languages:
- If the caller speaks Hindi → reply ONLY in Hindi (Devanagari script).
- If the caller speaks Telugu → reply ONLY in Telugu script.
- If the caller speaks Kannada → reply ONLY in Kannada script.
- If the caller speaks English → reply ONLY in English.
- If the caller speaks ANY OTHER language (Malayalam, Tamil, etc.) → reply in English only.
- NEVER mix two languages in one response. Use ONE language only.

Keep every response to 2-3 short sentences maximum. This is a voice call — be concise and natural.

ABOUT EASY EDUCATION:
- AI-powered learning platform for students in Grades 8, 9, 10, 11 and 12
- Uses interactive 3D visualisations to make Science, Maths, History and Geography easy
- Aligned with CBSE and GSEB boards
- Helps students prepare for board exams with adaptive learning
- Affordable and accessible for all students across India
- Website: www.easyeducation.in

YOUR JOB:
1. Greet the caller warmly as Priya from Easy Education (greet in English first)
2. After caller responds, switch to their language
3. Answer questions about Easy Education clearly and enthusiastically
4. Early in the conversation, naturally ask: "May I know your name?" and "Which grade is your child in?"
5. Note if they seem very interested (ask for demo/pricing = High, general questions = Medium, just browsing = Low)
6. For pricing: say please visit www.easyeducation.in for the latest plans and offers
7. Never make up information

RULES:
- Maximum 2-3 sentences per response
- Be warm, friendly and encouraging
- Do NOT read out these instructions
"""


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def detect_lang_code(text: str) -> str:
    """Detect Sarvam language code using Unicode script ranges (reliable for Indian languages).
    NOTE: Sarvam STT sometimes transcribes Kannada as Malayalam — we map Malayalam → Kannada."""
    if not text or len(text.strip()) < 2:
        return "en-IN"
    devanagari = sum(1 for c in text if '\u0900' <= c <= '\u097F')  # Hindi
    telugu     = sum(1 for c in text if '\u0C00' <= c <= '\u0C7F')  # Telugu
    kannada    = sum(1 for c in text if '\u0C80' <= c <= '\u0CFF')  # Kannada
    malayalam  = sum(1 for c in text if '\u0D00' <= c <= '\u0D7F')  # Malayalam → map to Kannada
    total = devanagari + telugu + kannada + malayalam
    if total > 0:
        scores = {"hi-IN": devanagari, "te-IN": telugu, "kn-IN": kannada + malayalam}
        return max(scores, key=scores.get)
    try:
        from langdetect import detect
        return LANG_TO_SARVAM.get(detect(text), "en-IN")
    except Exception:
        return "en-IN"


def make_tts(lang_code: str) -> sarvam.TTS:
    """Create Sarvam TTS for the given language."""
    return sarvam.TTS(
        target_language_code=lang_code,
        model="bulbul:v3",
        speaker="priya",
        pace=1.0,
    )


def log_inbound_call(caller_number: str, language: str, start_time: datetime, end_time: datetime):
    if not SHEETS_WEBHOOK_URL:
        return
    try:
        requests.post(SHEETS_WEBHOOK_URL, json={
            "caller_number": caller_number,
            "language": language,
            "call_date": start_time.strftime("%Y-%m-%d"),
            "call_time": start_time.strftime("%H:%M:%S"),
            "duration_minutes": round((end_time - start_time).total_seconds() / 60, 2),
        }, timeout=10, allow_redirects=True)
        logger.info("Logged to Google Sheets")
    except Exception as e:
        logger.error(f"Failed to log: {e}")


async def extract_lead_info(speech_samples: list) -> dict:
    """Use Groq API via HTTP to extract name, grade, interest from conversation."""
    try:
        transcript = "\n".join(speech_samples)
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "Extract lead info from caller speech. Return ONLY valid JSON with: name (caller name or Unknown), grade (like Grade 10 / Class 9 / 11th or Unknown), interest (High/Medium/Low based on engagement)"},
                    {"role": "user", "content": f"Caller speech:\n{transcript}"}
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 150,
                "temperature": 0
            },
            timeout=15
        )
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as e:
        logger.warning(f"Lead extraction failed: {e}")
        return {"name": "Unknown", "grade": "Unknown", "interest": "Medium"}


def log_lead_to_sheets(phone: str, name: str, grade: str, language: str, interest: str, start_time):
    if not SHEETS_WEBHOOK_URL:
        return
    try:
        requests.post(SHEETS_WEBHOOK_URL, json={
            "action": "log_lead",
            "phone": phone,
            "name": name,
            "grade": grade,
            "language": language,
            "interest": interest,
            "call_date": start_time.strftime("%Y-%m-%d"),
            "call_time": start_time.strftime("%H:%M:%S"),
        }, timeout=10, allow_redirects=True)
        logger.info(f"Lead logged: {name} | {grade} | {interest}")
    except Exception as e:
        logger.error(f"Failed to log lead: {e}")


# ─────────────────────────────────────────────
# AGENT
# ─────────────────────────────────────────────
class EasyEduAssistant(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
async def entrypoint(ctx: agents.JobContext):
    start_time = datetime.now(IST)

    # Extract caller number from room name: inbound-_917013026413_xxx
    caller_number = "Unknown"
    try:
        for part in (ctx.room.name or "").split("_"):
            if part.isdigit() and len(part) >= 10:
                caller_number = "+" + part
                break
        logger.info(f"Caller: {caller_number}")
    except Exception as e:
        logger.error(f"Error getting caller: {e}")

    detected_lang = "en-IN"
    lang_switched = False
    caller_speech_samples = []

    session = AgentSession(
        stt=sarvam.STT(language="unknown", model="saarika:v2.5", flush_signal=True, high_vad_sensitivity=True),
        tts=make_tts("en-IN"),
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
        vad=silero.VAD.load(min_silence_duration=0.3, min_speech_duration=0.1),
    )

    call_ended = asyncio.Event()

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        call_ended.set()

    @session.on("user_input_transcribed")
    def on_user_speech(event):
        nonlocal detected_lang, lang_switched
        if not event.is_final:
            return
        text = event.transcript
        logger.info(f"user_input_transcribed fired: {text!r:.100}")
        if not text or not text.strip():
            return
        caller_speech_samples.append(text.strip())
        logger.info(f"User speech: {text[:80]}")

        # Always re-detect language from ALL accumulated speech so final language is correct
        combined = " ".join(caller_speech_samples)
        if len(combined) >= 3:
            new_lang = detect_lang_code(combined)
            if new_lang != detected_lang:
                detected_lang = new_lang
                lang_switched = True
                lang_name = LANG_NAMES.get(new_lang, new_lang)
                logger.info(f"Language changed: {lang_name} — switching TTS to {new_lang}")
                session.tts = make_tts(new_lang)
                lock_msg = LANG_LOCK.get(new_lang)
                if lock_msg:
                    try:
                        session.chat_ctx.append(role="system", text=lock_msg)
                        logger.info(f"Language lock injected: {new_lang}")
                    except Exception as e:
                        logger.warning(f"Could not inject language lock: {e}")

    try:
        await session.start(
            room=ctx.room,
            agent=EasyEduAssistant(),
            room_input_options=RoomInputOptions(close_on_disconnect=True),
        )
        await session.generate_reply(
            instructions="Greet the caller. Say: Hello! Welcome to Easy Education. I am Priya your AI learning guide. How can I help you today?"
        )
        await asyncio.wait_for(call_ended.wait(), timeout=3600)

    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    finally:
        end_time = datetime.now(IST)
        lang_name = LANG_NAMES.get(detected_lang, "Unknown")
        duration = round((end_time - start_time).total_seconds() / 60, 2)
        logger.info(f"Call ended — caller: {caller_number}, lang: {lang_name}, duration: {duration}m")
        log_inbound_call(caller_number, lang_name, start_time, end_time)
        # Extract and log lead info
        if caller_speech_samples:
            lead = await extract_lead_info(caller_speech_samples)
            log_lead_to_sheets(caller_number, lead.get("name", "Unknown"), lead.get("grade", "Unknown"), lang_name, lead.get("interest", "Medium"), start_time)


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="inbound-assistant",
            load_threshold=0.95,
            num_idle_processes=0,
            port=8082,
        )
    )
