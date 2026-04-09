"""
setup_dispatch.py
=================
Creates the SIP inbound trunk + dispatch rule in LiveKit.
Run this AUTOMATICALLY via start.sh — no need to run manually.

If you need to run manually:
    cd ~/livekit-project && python3 setup_dispatch.py
"""

import asyncio
import os
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env")

async def setup():
    lk = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )

    # Step 1: Create SIP inbound trunk (filter by number, no auth challenge)
    trunk = await lk.sip.create_sip_inbound_trunk(
        api.CreateSIPInboundTrunkRequest(
            trunk=api.SIPInboundTrunkInfo(
                name="VoBiz Inbound",
                numbers=["+918065481599"],
            )
        )
    )
    print(f"✅ Trunk created: {trunk.sip_trunk_id}")

    # Step 2: Create dispatch rule using the new trunk ID
    rule = await lk.sip.create_sip_dispatch_rule(
        api.CreateSIPDispatchRuleRequest(
            rule=api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                    room_prefix="inbound-",
                )
            ),
            trunk_ids=[trunk.sip_trunk_id],
            name="Inbound Rule",
            room_config=api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name="inbound-assistant",
                    )
                ]
            ),
        )
    )
    print(f"✅ Dispatch rule created: {rule.sip_dispatch_rule_id}")
    await lk.aclose()

asyncio.run(setup())
