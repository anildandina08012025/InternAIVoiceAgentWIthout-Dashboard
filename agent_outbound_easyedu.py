"""
agent_outbound_easyedu.py
==========================
EasyEducation AI Voice Agent — Outbound Calls
- Persona: Priya from Easy Education
- Multilingual: Detects caller language, switches Sarvam TTS to match
- STT: Sarvam saarika:v2.5
- TTS: Sarvam bulbul:v3, speaker priya
- LLM: Groq llama-3.3-70b-versatile
- Triggered by Google Sheets → call_webhook.py → LiveKit dispatch
- Supports Topic-based calls: pass topic + language in metadata
"""

import logging
import os
import json
from dotenv import load_dotenv
from livekit import agents, api
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import sarvam, silero
from livekit.plugins import groq

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("easyedu-outbound")

OUTBOUND_TRUNK_ID = os.getenv("OUTBOUND_TRUNK_ID")

# ─────────────────────────────────────────────
# LANGUAGE MAPS — supported: English, Hindi, Telugu, Kannada
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

# Language name → Sarvam code (used for topic-based calls)
NAME_TO_CODE = {
    "Hindi":   "hi-IN",
    "Telugu":  "te-IN",
    "Kannada": "kn-IN",
    "English": "en-IN",
}

# Injected into chat context when language is detected — forces Groq to stay in that language
LANG_LOCK = {
    "hi-IN": "LANGUAGE LOCK ACTIVE: The person is speaking Hindi. From this point forward, ALL your responses must be EXCLUSIVELY in Hindi (Devanagari script हिंदी). Do not use English or any other language. Every single word must be Hindi.",
    "te-IN": "LANGUAGE LOCK ACTIVE: The person is speaking Telugu. From this point forward, ALL your responses must be EXCLUSIVELY in Telugu (తెలుగు script). Do not use English or any other language. Every single word must be Telugu.",
    "kn-IN": "LANGUAGE LOCK ACTIVE: The person is speaking Kannada. From this point forward, ALL your responses must be EXCLUSIVELY in Kannada (ಕನ್ನಡ script). Do not use English or any other language. Every single word must be Kannada.",
    "en-IN": "Continue responding in English only.",
}

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are Priya, a friendly voice AI assistant for Easy Education — India's AI-powered ed-tech platform.
You have called this person to tell them about Easy Education.

STRICT LANGUAGE RULE — You ONLY support these 4 languages:
- If the person speaks Hindi → reply ONLY in Hindi (Devanagari script).
- If the person speaks Telugu → reply ONLY in Telugu script.
- If the person speaks Kannada → reply ONLY in Kannada script.
- If the person speaks English → reply ONLY in English.
- If the person speaks ANY OTHER language (Malayalam, Tamil, etc.) → reply in English only.
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
1. ALWAYS greet in the specified language — stick to that language throughout
2. If a specific topic is given, focus the entire conversation on that topic
3. Briefly explain what Easy Education offers related to the topic
4. Ask one follow-up question such as:
   - "Do you have a child in grades 8 to 12?"
   - "Would you like to know how our 3D lessons work?"
   - "Would you like to try a free demo?"
5. For pricing questions say: please visit www.easyeducation.in for the latest plans and offers
6. Never make up information — only share what is listed above
7. If the person is not interested, thank them politely and end the call

RULES:
- Maximum 2-3 sentences per response
- Be warm, friendly and not pushy
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


# ─────────────────────────────────────────────
# AGENT CLASS
# ─────────────────────────────────────────────
class EasyEduOutboundAssistant(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
async def entrypoint(ctx: agents.JobContext):
    logger.info(f"EasyEdu outbound call — room: {ctx.room.name}")

    # Get phone number, topic, language from dispatch metadata
    phone_number = None
    topic = ""
    language_name = "English"
    try:
        if ctx.job.metadata:
            data = json.loads(ctx.job.metadata)
            phone_number = data.get("phone_number")
            topic = data.get("topic", "").strip()
            language_name = data.get("language", "English").strip()
            logger.info(f"Calling: {phone_number} | topic: {topic} | language: {language_name}")
    except Exception as e:
        logger.error(f"Error parsing metadata: {e}")

    if not phone_number:
        logger.error("No phone_number in metadata — aborting")
        return

    if not OUTBOUND_TRUNK_ID:
        logger.error("OUTBOUND_TRUNK_ID not set in .env — aborting")
        return

    # Set language from the start based on specified language
    lang_code = NAME_TO_CODE.get(language_name, "en-IN")
    detected_lang = lang_code
    lang_switched = False
    speech_samples = []

    session = AgentSession(
        stt=sarvam.STT(language="unknown", model="saarika:v2.5", flush_signal=True, high_vad_sensitivity=True),
        tts=make_tts(lang_code),
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
        vad=silero.VAD.load(min_silence_duration=0.3, min_speech_duration=0.1),
    )

    @session.on("user_input_transcribed")
    def on_user_speech(event):
        nonlocal detected_lang, lang_switched
        if not event.is_final:
            return
        text = event.transcript
        if not text or not text.strip():
            return
        logger.info(f"User speech: {text[:80]}")

        speech_samples.append(text.strip())
        combined = " ".join(speech_samples)
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

    await session.start(
        room=ctx.room,
        agent=EasyEduOutboundAssistant(),
        room_input_options=RoomInputOptions(close_on_disconnect=True),
    )

    # Dial out via VoBiz SIP trunk
    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=OUTBOUND_TRUNK_ID,
                sip_call_to=phone_number,
                participant_identity=f"sip_{phone_number.replace('+', '')}",
                wait_until_answered=True,
            )
        )
        logger.info(f"Call answered by {phone_number}")

        # Greet in specified language about the specific topic
        if topic:
            greeting_instruction = (
                f"You are calling specifically to talk about: {topic}. "
                f"Greet in {language_name} language ONLY. Introduce yourself as Priya from Easy Education, "
                f"then naturally bring up the topic. Keep it to 2-3 sentences. "
                f"Speak ONLY in {language_name} — do not use English unless language is English."
            )
        else:
            greeting_instruction = (
                f"Greet in {language_name} language ONLY. Say: Hello! This is Priya calling from Easy Education. "
                f"We help students in grades 8 to 12 learn better with AI-powered 3D lessons. "
                f"Do you have a child studying in school right now? "
                f"Speak ONLY in {language_name}."
            )
        await session.generate_reply(instructions=greeting_instruction)
        logger.info(f"Greeting done — topic: {topic} | language: {language_name}")

    except Exception as e:
        logger.error(f"Failed to place outbound call to {phone_number}: {e}")
        ctx.shutdown()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outbound-caller",
            load_threshold=0.95,
            num_idle_processes=1,
            port=8081,
        )
    )
