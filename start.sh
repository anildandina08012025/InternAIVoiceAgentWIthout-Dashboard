#!/bin/bash
# =============================================
# start.sh — EasyEducation AI Voice System
# One-command startup after EC2 restart
# =============================================

set -e
cd ~/livekit-project

echo "============================================"
echo "  EasyEducation AI Voice System — Starting"
echo "============================================"

# Step 1: Restart Docker containers (Redis + LiveKit + SIP)
echo ""
echo "▶ Step 1: Restarting Docker containers..."
sudo docker-compose down
sudo docker-compose up -d

# Step 2: Wait for LiveKit to be ready
echo ""
echo "▶ Step 2: Waiting for LiveKit to start (15 seconds)..."
sleep 15

# Step 3: Recreate SIP trunk + dispatch rule (Redis is wiped on restart)
echo ""
echo "▶ Step 3: Setting up SIP trunk + dispatch rule..."
python3 setup_dispatch.py

# Step 4: Kill any old agent/webhook processes and free ports
echo ""
echo "▶ Step 4: Stopping old processes..."
pkill -f "agent_outbound_easyedu.py" 2>/dev/null || true
pkill -f "agent_inbound_easyedu.py"  2>/dev/null || true
pkill -f "call_webhook.py"           2>/dev/null || true
# Keep agent.py alive as fallback? No — kill it too to avoid port conflict
pkill -f "agent.py"                  2>/dev/null || true
pkill -f "agent_inbound_selfhost.py" 2>/dev/null || true
sleep 2
fuser -k 8081/tcp 2>/dev/null || true
fuser -k 8082/tcp 2>/dev/null || true
fuser -k 8090/tcp 2>/dev/null || true
sleep 2

# Step 5: Start all three services
echo ""
echo "▶ Step 5: Starting EasyEdu agents + webhook server..."

nohup python3 agent_outbound_easyedu.py start > outbound.log 2>&1 &
echo "  ✅ Outbound agent started (port 8081) → outbound.log"

nohup python3 agent_inbound_easyedu.py start > inbound.log 2>&1 &
echo "  ✅ Inbound agent started  (port 8082) → inbound.log"

nohup python3 call_webhook.py > webhook.log 2>&1 &
echo "  ✅ Call webhook started   (port 8090) → webhook.log"

echo ""
echo "============================================"
echo "  ✅ All services started!"
echo "============================================"
echo ""
echo "Logs (last 3 lines each):"
sleep 5
echo "--- outbound.log ---"
tail -3 outbound.log 2>/dev/null || echo "(no output yet)"
echo "--- inbound.log ---"
tail -3 inbound.log  2>/dev/null || echo "(no output yet)"
echo "--- webhook.log ---"
tail -3 webhook.log  2>/dev/null || echo "(no output yet)"
echo ""
echo "To check live logs:"
echo "  tail -f ~/livekit-project/outbound.log"
echo "  tail -f ~/livekit-project/inbound.log"
echo "  tail -f ~/livekit-project/webhook.log"
