"""
setup_outbound_trunk.py
=======================
Creates the LiveKit SIP outbound trunk used by agent_outbound_easyedu.py.

Run once after LiveKit and livekit-sip are running:
    python3 setup_outbound_trunk.py

Then copy the printed SIP trunk ID into .env as OUTBOUND_TRUNK_ID.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from livekit import api


load_dotenv(".env")


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


async def setup():
    lk = api.LiveKitAPI(
        url=require_env("LIVEKIT_URL"),
        api_key=require_env("LIVEKIT_API_KEY"),
        api_secret=require_env("LIVEKIT_API_SECRET"),
    )

    try:
        trunk = api.SIPOutboundTrunkInfo(
            name=os.getenv("VOBIZ_OUTBOUND_TRUNK_NAME", "VoBiz Outbound"),
            address=require_env("VOBIZ_SIP_DOMAIN"),
            numbers=[require_env("VOBIZ_OUTBOUND_NUMBER")],
            auth_username=require_env("VOBIZ_USERNAME"),
            auth_password=require_env("VOBIZ_PASSWORD"),
            destination_country=os.getenv("VOBIZ_DESTINATION_COUNTRY", "IN"),
        )

        request = api.CreateSIPOutboundTrunkRequest(trunk=trunk)

        create_fn = getattr(lk.sip, "create_outbound_trunk", None)
        if create_fn is None:
            create_fn = lk.sip.create_sip_outbound_trunk

        created = await create_fn(request)
        print(f"Outbound trunk created: {created.sip_trunk_id}")
        print("Add this to .env:")
        print(f"OUTBOUND_TRUNK_ID={created.sip_trunk_id}")
    finally:
        await lk.aclose()


asyncio.run(setup())
