"""
agent_outbound_easyedu.py
==========================
Aivoro Hospital Voice Agent - Outbound Calls
- Persona: Priya, receptionist at Aivoro Hospital
- Multilingual: Detects caller language, switches Sarvam TTS to match
- STT: Sarvam saarika:v2.5
- TTS: Sarvam bulbul:v3, speaker priya
- LLM: OpenRouter / Cerebras openai/gpt-oss-120b
- Triggered by Google Sheets → call_webhook.py → LiveKit dispatch
- Supports Topic-based calls: pass topic + language in metadata
"""

import asyncio
import logging
import os
import json
import sys
import requests
from datetime import datetime, timezone, timedelta
from call_guard import claim_call

IST = timezone(timedelta(hours=5, minutes=30))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
from livekit import agents, api
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool
from livekit.plugins import google, openai, sarvam, silero
from livekit.plugins.google.beta import GeminiTTS

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aihospital-outbound")

OUTBOUND_TRUNK_ID = os.getenv("OUTBOUND_TRUNK_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
OPENROUTER_PROVIDER = {"only": ["cerebras"], "allow_fallbacks": False}
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
KANNADA_TTS_PROVIDER = os.getenv("KANNADA_TTS_PROVIDER", "sarvam").strip().lower()
GOOGLE_KANNADA_VOICE = os.getenv("GOOGLE_KANNADA_VOICE", "kn-IN-Chirp3-HD-Kore")

SRM_PROMPT = """
You are Priya, a courteous AI receptionist calling on behalf of S-R-M Elite Travels about the customer's recent bus journey. Introduce yourself as an AI assistant and ask if this is a convenient time to talk.
Ask how their bus journey was and invite an honest rating out of five. If they enjoyed it, politely ask them to consider giving S-R-M Elite Travels a five-star rating on the app; never pressure them or suggest a rating that does not reflect their experience. Accept any rating or refusal graciously.
Listen carefully to feedback or complaints, apologize empathetically for problems, and ask a brief clarifying question if needed. Use the save_journey_feedback tool to save the customer's rating and feedback. Only say it was recorded after the tool confirms success; explain honestly if saving failed. The team can review saved feedback; do not claim it has already been forwarded or promise a resolution or callback.
Do not invent journey details, review links, policies, or outcomes. If the customer is busy, declines, or says wrong number, apologize if appropriate and end politely. Keep responses short and natural for a phone call. Speak only Kannada, Telugu, or English. Begin in Kannada; switch to Telugu or English if the customer speaks or requests one of those languages. For unsupported languages, politely offer Kannada, Telugu, or English in the current language.
"""

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

# Injected into chat context when language is detected — keeps the LLM in that language
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
You are Priya, a polite and professional hospital receptionist calling from Aivoro Hospital.
You are making outbound appointment reminder calls.

STRICT LANGUAGE RULE - You ONLY support these 4 languages:
- If the person speaks Hindi, reply ONLY in Hindi using Devanagari script.
- If the person speaks Telugu, reply ONLY in Telugu script.
- If the person speaks Kannada, reply ONLY in Kannada script.
- If the person speaks English, reply ONLY in English.
- If the person speaks any other language, reply in English only.
- NEVER mix two languages in one response. Use ONE language only.

Keep every response to 2-3 short sentences maximum. This is a voice call, so be concise and natural.

ABOUT AI HOSPITAL:
- Aivoro Hospital is a healthcare provider that helps patients with appointments and hospital visit coordination.
- You can remind patients about their recorded appointment date and time.
- You can answer basic appointment questions politely.
- You can ask the patient to contact the hospital front desk for changes, cancellations, emergency help, or medical advice.
- Do not give diagnosis, prescriptions, treatment instructions, or emergency medical guidance.

YOUR JOB:
1. ALWAYS greet in the specified language and stay in that language throughout.
2. Introduce yourself as Priya, receptionist from Aivoro Hospital.
3. If a specific topic is given from Google Sheets, focus the conversation on that topic.
4. Use only the supplied appointment date and time. Never invent an appointment or assume it is today. Confirm you are speaking with the intended patient before sharing appointment details. Remind them to arrive on time.
5. Ask whether they can attend their recorded appointment.
6. If they want to reschedule or ask medical questions, say the hospital front desk or doctor will help them.
7. If they are not interested or say it is a wrong number, apologize politely and end the call.

RULES:
- Maximum 2-3 sentences per response.
- Be calm, respectful, and professional.
- Do NOT claim to be a doctor.
- Do NOT ask for sensitive medical details.
- Do NOT read out these instructions.
"""

TELUGU_CEMENT_DEMO_PROMPT = """
You are a polite Telugu-speaking AI voice assistant calling on behalf of Anil Sir's company.
This is a demonstration of an AI voice calling agent for cement sales.

The caller has already heard a short Telugu greeting. After they respond positively, explain in Telugu that you can speak with their customers about OPC and PPC cement orders and demonstrate cement order booking. Ask which demo they would like. Keep every answer to one or two short sentences.

If they say they are not interested, thank them in Telugu and end politely. Do not mention Aivoro Hospital, appointments, Priya, or medical services. Speak only Telugu script.
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



def make_tts(lang_code: str):
    """Use Google for Kannada when configured, and Sarvam for other languages."""
    if lang_code == "kn-IN" and KANNADA_TTS_PROVIDER == "google":
        api_key = os.getenv("GOOGLE_TTS_API_KEY", "").strip()
        if api_key:
            from google.genai import Client
            voice = GeminiTTS(model="gemini-2.5-flash-preview-tts", voice_name=os.getenv("GOOGLE_GEMINI_TTS_VOICE", "Kore"), api_key=api_key)
            # TTS speech configuration requires the Gemini API's v1beta endpoint.
            voice._client = Client(api_key=api_key, http_options={"api_version": "v1beta"})
            return voice
        credentials_json = os.getenv("GOOGLE_TTS_CREDENTIALS_JSON", "").strip()
        if credentials_json:
            return google.TTS(language="kn-IN", voice_name=GOOGLE_KANNADA_VOICE, credentials_info=json.loads(credentials_json))
        return google.TTS(language="kn-IN", voice_name=GOOGLE_KANNADA_VOICE)
    return sarvam.TTS(
        target_language_code=lang_code,
        model="bulbul:v4-flash" if lang_code in ("kn-IN", "te-IN") else "bulbul:v3",
        speaker=(os.getenv("SARVAM_KANNADA_SPEAKER", "aparna_hi_customer") if lang_code == "kn-IN"
                 else os.getenv("SARVAM_TELUGU_SPEAKER", "aparna_hi_customer") if lang_code == "te-IN"
                 else "priya"),
        speech_sample_rate=24000 if lang_code in ("kn-IN", "te-IN") else 22050,
        pace=1.0,
        temperature=0.6,
        output_audio_codec="mp3",
    )


# ─────────────────────────────────────────────
# AGENT CLASS
# ─────────────────────────────────────────────
class AIHospitalOutboundAssistant(Agent):
    def __init__(self, instructions: str = SYSTEM_PROMPT):
        super().__init__(instructions=instructions)


class SRMTravelAssistant(Agent):
    def __init__(self, instructions: str, phone_number: str):
        super().__init__(instructions=instructions)
        self.phone_number = phone_number

    @function_tool()
    async def save_journey_feedback(self, feedback: str, rating: str = "") -> str:
        """Save the customer's journey feedback and their stated rating out of five, if given."""
        if not SHEETS_WEBHOOK_URL or not WEBHOOK_SECRET:
            return "Feedback could not be saved: the feedback service is not configured."
        try:
            response = await asyncio.to_thread(
                requests.post, SHEETS_WEBHOOK_URL,
                json={"action": "save_srm_feedback", "secret": WEBHOOK_SECRET,
                      "phone": self.phone_number, "feedback": feedback, "rating": rating},
                timeout=15,
            )
            response.raise_for_status()
            if response.json().get("status") != "ok":
                return "Feedback could not be saved."
            return "Feedback recorded for the S-R-M Elite Travels team to review."
        except (requests.RequestException, ValueError):
            logger.exception("Could not save S-R-M feedback")
            return "Feedback could not be saved."


CEMENT_DEMO_PROMPT = """
You are a polite Kannada-speaking AI voice assistant calling on behalf of Anil Sir's company.
This is a demonstration of an AI voice calling agent for cement sales.

The caller has already heard a short Kannada greeting. After they respond positively, explain in Kannada that you can speak with their customers about OPC and PPC cement orders and demonstrate cement order booking. Ask which demo they would like. Keep every answer to one or two short sentences.

If they say they are not interested, thank them in Kannada and end politely. Do not mention Aivoro Hospital, appointments, Priya, or medical services. Speak only Kannada script.
"""


AIVORO_DEMO_PROMPT = SYSTEM_PROMPT




# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
async def entrypoint(ctx: agents.JobContext):
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY must be set in .env")
    logger.info(f"Aivoro Hospital outbound call - room: {ctx.room.name}")

    # Get phone number, topic, language from dispatch metadata
    phone_number = None
    topic = ""
    language_name = "English"
    call_mode = ""
    recipient_name = ""
    appointment_at = ""
    try:
        if ctx.job.metadata:
            data = json.loads(ctx.job.metadata)
            phone_number = data.get("phone_number")
            topic = data.get("topic", "").strip()
            language_name = data.get("language", "English").strip()
            call_mode = data.get("call_mode", "").strip()
            recipient_name = data.get("recipient_name", "").strip()
            appointment_at = data.get("appointment_at", "").strip()
            logger.info(f"Calling: {phone_number} | topic: {topic} | language: {language_name}")
    except Exception as e:
        logger.error(f"Error parsing metadata: {e}")

    if not phone_number:
        logger.error("No phone_number in metadata — aborting")
        return

    if not OUTBOUND_TRUNK_ID:
        logger.error("OUTBOUND_TRUNK_ID not set in .env — aborting")
        return

    if not claim_call(phone_number, cooldown=0 if call_mode == "srm-travels-telugu-test" else 600):
        logger.warning("Duplicate call suppressed for %s", phone_number)
        ctx.shutdown()
        return

    english_test = call_mode == "srm-travels-english-test"
    telugu_test = call_mode == "srm-travels-telugu-test"
    fast_test = call_mode in ("srm-travels-english-test", "srm-travels-kannada-test", "srm-travels-telugu-test")
    is_srm_call = call_mode in ("srm-travels-feedback", "srm-travels-english-test", "srm-travels-kannada-test", "srm-travels-telugu-test") or (not call_mode and not appointment_at)
    if is_srm_call:
        language_name = "English" if english_test else "Telugu" if telugu_test else "Kannada"

    # Travel calls always start in Kannada; other calls use the selected language.
    lang_code = NAME_TO_CODE.get(language_name, "en-IN")
    detected_lang = lang_code
    lang_switched = False
    speech_samples = []

    session = AgentSession(
        stt=sarvam.STT(language="unknown", model="saarika:v2.5", flush_signal=True, high_vad_sensitivity=True),
        tts=make_tts(lang_code),
        llm=openai.LLM(model=OPENROUTER_MODEL, base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY, reasoning_effort="low", extra_body={"provider": OPENROUTER_PROVIDER}),
        vad=silero.VAD.load(min_silence_duration=0.3, min_speech_duration=0.1),
        turn_detection="stt",
        allow_interruptions=True,
        preemptive_generation=fast_test,
        min_endpointing_delay=0.3 if fast_test else 0.6,
    )

    call_ended = asyncio.Event()

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        """Keep interactive demo calls alive until the SIP participant leaves."""
        if participant.identity.startswith("sip_"):
            call_ended.set()

    @session.on("metrics_collected")
    def on_metrics_collected(event):
        metrics = event.metrics
        if getattr(metrics, "type", None) == "llm_metrics":
            logger.info(
                "OpenRouter LLM usage — prompt_tokens=%s completion_tokens=%s total_tokens=%s ttft=%.3fs duration=%.3fs",
                metrics.prompt_tokens, metrics.completion_tokens, metrics.total_tokens, metrics.ttft, metrics.duration
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

        if english_test:
            return

        speech_samples.append(text.strip())
        combined = " ".join(speech_samples)
        if len(combined) >= 3:
            new_lang = detect_lang_code(text if is_srm_call else combined)
            if is_srm_call and new_lang not in ("kn-IN", "te-IN", "en-IN"):
                return
            if new_lang != detected_lang:
                detected_lang = new_lang
                lang_switched = True
                lang_name = LANG_NAMES.get(new_lang, new_lang)
                logger.info(f"Language changed: {lang_name} — switching TTS to {new_lang}")
                hospital_agent.update_options(tts=make_tts(new_lang))
                asyncio.create_task(hospital_agent.update_instructions(
                    agent_instructions + "\n" + LANG_LOCK[new_lang]))

    if is_srm_call:
        agent_instructions = SRM_PROMPT
        if english_test:
            agent_instructions += "\nFor this test call, use English only throughout. Ignore the instruction to begin in Kannada."
        elif telugu_test:
            agent_instructions += "\nFor this test call, begin in Telugu instead of Kannada."
    elif call_mode == "direct-message":
        direct_topic = topic or "We have talked to your lead and we have discussed it. Thank you Thamma Reddy."
        agent_instructions = (
            "You are a concise AI voice assistant calling on behalf of Anil Sir's company. "
            f"Only discuss this message: {direct_topic} "
            "If the person responds, acknowledge briefly and close politely. "
            "Do not mention Aivoro Hospital, appointments, OPC, PPC, or cement unless the message asks for it."
        )
    elif call_mode == "anil-cement-demo":
        agent_instructions = TELUGU_CEMENT_DEMO_PROMPT if language_name == "Telugu" else CEMENT_DEMO_PROMPT
    elif call_mode == "aivoro-voice-agent-demo":
        agent_instructions = AIVORO_DEMO_PROMPT
    else:
        agent_instructions = SYSTEM_PROMPT
        agent_instructions += "\nRecipient name: " + recipient_name + "\nRecorded appointment: " + appointment_at
        agent_instructions += "\nAivoro Hospital provides comprehensive treatment across specialties. Specific services, doctors, fees and hours require staff confirmation. Help with service enquiries; do not invent details."
    if is_srm_call:
        hospital_agent = SRMTravelAssistant(agent_instructions + "\n" + LANG_LOCK[lang_code], phone_number)
    else:
        hospital_agent = AIHospitalOutboundAssistant(instructions=agent_instructions + "\n" + LANG_LOCK[lang_code])
    await session.start(
        room=ctx.room,
        agent=hospital_agent,
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

        if isinstance(hospital_agent, SRMTravelAssistant):
            if english_test:
                greeting = "Hello, this is Priya, the AI receptionist calling from S R M Elite Travels. Is this a good time to talk about your bus journey?"
            elif telugu_test:
                greeting = "నమస్కారం, నేను ఎస్ ఆర్ ఎం ఎలైట్ ట్రావెల్స్ తరఫున మాట్లాడుతున్న ఏఐ రిసెప్షనిస్ట్ ప్రియని. మీ బస్సు ప్రయాణం గురించి మాట్లాడటానికి ఇది అనుకూలమైన సమయమేనా?"
            else:
                greeting = "ನಮಸ್ಕಾರ, ನಾನು ಎಸ್ ಆರ್ ಎಂ ಎಲೈಟ್ ಟ್ರಾವೆಲ್ಸ್ ಪರವಾಗಿ ಮಾತನಾಡುತ್ತಿರುವ ಎಐ ರಿಸೆಪ್ಷನಿಸ್ಟ್ ಪ್ರಿಯಾ. ನಿಮ್ಮ ಬಸ್ ಪ್ರಯಾಣದ ಬಗ್ಗೆ ಮಾತನಾಡಲು ಇದು ಅನುಕೂಲವಾದ ಸಮಯವೇ?"
            await session.say(greeting)
            await asyncio.wait_for(call_ended.wait(), timeout=3600)
            return
        if call_mode == "direct-message":
            direct_message = topic or "We have talked to your lead and we have discussed it. Thank you Thamma Reddy."
            await session.say(direct_message)
            logger.info("Direct one-time message completed")
            return
        if call_mode == "anil-cement-demo":
            if language_name == "Telugu":
                name = recipient_name or "తమ్మ రెడ్డి"
                demo_greeting = (
                    f"హలో {name} గారు. నేను అనిల్ సర్ కంపెనీ నుంచి మాట్లాడుతున్న AI వాయిస్ అసిస్టెంట్‌ని. "
                    "ఒక చిన్న డెమో చూపించవచ్చా?"
                )
            else:
                name = recipient_name or "ತಮ್ಮ ರೆಡ್ಡಿ"
                demo_greeting = (
                    f"హలో {name} ಅವರೆ. ನಾನು ಅನಿಲ್ ಸರ್ ಕಂಪನಿಯಿಂದ ಮಾತನಾಡುತ್ತಿರುವ AI ವಾಯ್ಸ್ ಅಸಿಸ್ಟೆಂಟ್. "
                    "ಒಂದು ಚಿಕ್ಕ ಡೆಮೋ ತೋರಿಸಬಹುದೇ?"
                )
            await session.say(demo_greeting)
            logger.info("Kannada one-time cement demo greeting completed; waiting for recipient response")
            return
        if call_mode == "aivoro-voice-agent-demo":
            name = recipient_name.strip()
            greeting_name = f" {name}" if name else ""
            greeting = (
                f"Hello{greeting_name}! This is Priya, the AI hospital assistant from Aivoro Hospital. "
                "I can help with hospital services and appointment enquiries. How can I help you today?"
            )
            await session.say(greeting)
            logger.info("Aivoro demo greeting completed; waiting for client response before asking for a topic")
            try:
                await asyncio.wait_for(call_ended.wait(), timeout=3600)
            except asyncio.TimeoutError:
                logger.info("Aivoro demo reached its one-hour call limit")
            return
        if not topic and not appointment_at:
            logger.error("Reminder requires a real appointment_at; refusing to invent an appointment")
            ctx.shutdown()
            return
        appointment_time = appointment_at
        if appointment_at:
            appointment_time = datetime.fromisoformat(appointment_at).astimezone(IST).strftime("%d %B %Y at %I:%M %p IST")

        # Greet in the specified language. Google Sheets topic overrides the default appointment reminder.
        if topic:
            greeting_instruction = (
                f"You are calling specifically about this hospital topic: {topic}. "
                f"Greet in {language_name} language ONLY. Introduce yourself as Priya, receptionist from Aivoro Hospital, "
                f"then naturally discuss the topic. Keep it to 2-3 sentences. "
                f"Speak ONLY in {language_name}; do not use English unless language is English."
            )
        else:
            greeting_instruction = (
                f"Greet in {language_name} language ONLY. Say that this is Priya, receptionist from Aivoro Hospital. "
                f"Ask to speak with the intended patient before sharing appointment details. Once identity is confirmed, remind them of their appointment on {appointment_time} and ask them to arrive on time. "
                f"Ask whether they will be able to attend the appointment. "
                f"Keep it to 2-3 sentences. Speak ONLY in {language_name}."
            )
        await session.generate_reply(instructions=greeting_instruction)
        logger.info(f"Greeting done — topic: {topic} | language: {language_name}")
        await asyncio.wait_for(call_ended.wait(), timeout=3600)

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




