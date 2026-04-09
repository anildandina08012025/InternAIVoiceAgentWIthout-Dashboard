"""
call_webhook.py
===============
Flask webhook server — listens on port 8090.
Google Apps Script calls this when a new phone number is added to Outbound tab.
Triggers an outbound call via LiveKit agent dispatch.
Supports topic + language for targeted outbound calls.
"""

import logging
import os
import json
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("call-webhook")

app = Flask(__name__)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "easyedu-secret-2026")


async def dispatch_call(phone_number: str, topic: str = "", language: str = "English"):
    """Dispatch an outbound call to the given phone number via LiveKit."""
    lk = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL", "ws://localhost:7880"),
        api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
        api_secret=os.getenv("LIVEKIT_API_SECRET", "secret"),
    )
    room_name = f"outbound-{phone_number.replace('+', '').replace(' ', '')}"
    try:
        dispatch = await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="outbound-caller",
                room=room_name,
                metadata=json.dumps({"phone_number": phone_number, "topic": topic, "language": language}),
            )
        )
        logger.info(f"Call dispatched — number: {phone_number}, topic: {topic}, lang: {language}, dispatch_id: {dispatch.id}")
        return True
    except Exception as e:
        logger.error(f"Failed to dispatch call to {phone_number}: {e}")
        return False
    finally:
        await lk.aclose()


@app.route("/trigger-call", methods=["POST"])
def trigger_call():
    """
    Endpoint called by Google Apps Script when a new number is added.
    Expected JSON: { "phone_number": "+91XXXXXXXXXX", "topic": "...", "language": "Hindi", "secret": "easyedu-secret-2026" }
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No JSON body"}), 400

        # Validate secret
        if data.get("secret") != WEBHOOK_SECRET:
            logger.warning(f"Invalid secret from {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        phone_number = data.get("phone_number", "").strip()
        topic = data.get("topic", "").strip()
        language = data.get("language", "English").strip()

        if not phone_number:
            return jsonify({"status": "error", "message": "phone_number required"}), 400

        logger.info(f"Trigger received for: {phone_number} | topic: {topic} | lang: {language}")

        # Run async dispatch in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(dispatch_call(phone_number, topic, language))
        loop.close()

        if success:
            return jsonify({"status": "success", "phone_number": phone_number}), 200
        else:
            return jsonify({"status": "error", "message": "Dispatch failed"}), 500

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()}), 200


if __name__ == "__main__":
    logger.info("Starting call webhook server on port 8090...")
    app.run(host="0.0.0.0", port=8090, debug=False)
