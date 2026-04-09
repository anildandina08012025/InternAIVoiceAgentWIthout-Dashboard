# AWS EC2 Setup + LiveKit Self-Hosting Guide

Complete step-by-step guide to create an AWS EC2 instance and self-host LiveKit for AI voice calling.

---

## PART 1 — Create AWS EC2 Instance

### Step 1 — Create AWS Account
1. Go to https://aws.amazon.com
2. Click **Create an AWS Account**
3. Fill in email, password, account name
4. Add payment method (credit/debit card)
5. Choose **Basic Support (Free)**
6. Verify phone number

---

### Step 2 — Go to EC2 Dashboard
1. Log in to https://console.aws.amazon.com
2. In the search bar type **EC2**
3. Click **EC2** from results
4. Make sure region is **Asia Pacific (Mumbai) — ap-south-1** (top right corner)

---

### Step 3 — Launch a New Instance
1. Click **Launch instances** (orange button)
2. Fill in the details:

| Field | Value |
|-------|-------|
| Name | `livekit-vobiz` |
| OS | Ubuntu Server 22.04 LTS |
| Architecture | 64-bit (x86) |
| Instance type | `t2.micro` (Free Tier eligible) |

---

### Step 4 — Create Key Pair (for SSH login)
1. Under **Key pair (login)** click **Create new key pair**
2. Fill in:
   - Key pair name: `livekit-key`
   - Key pair type: RSA
   - Private key format: `.pem`
3. Click **Create key pair**
4. A file `livekit-key.pem` will download automatically
5. **Save it safely** — you need this to SSH into your server

> ⚠️ IMPORTANT: Never share this .pem file with anyone. If lost, you cannot SSH into your server.

---

### Step 5 — Configure Security Group (Firewall Rules)
1. Under **Network settings** click **Edit**
2. Add the following inbound rules:

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| SSH | TCP | 22 | 0.0.0.0/0 | SSH access |
| Custom TCP | TCP | 7880 | 0.0.0.0/0 | LiveKit WebSocket |
| Custom TCP | TCP | 7881 | 0.0.0.0/0 | LiveKit WebRTC |
| Custom UDP | UDP | 5060 | 0.0.0.0/0 | SIP signalling |
| Custom TCP | TCP | 5060 | 0.0.0.0/0 | SIP signalling |
| Custom UDP | UDP | 10000-10100 | 0.0.0.0/0 | RTP media |
| Custom UDP | UDP | 50000-50200 | 0.0.0.0/0 | WebRTC media |

---

### Step 6 — Configure Storage
1. Under **Configure storage**
2. Set to **20 GB** (default 8GB is too small)
3. Volume type: `gp3`

---

### Step 7 — Launch the Instance
1. Click **Launch instance** (orange button)
2. Click **View all instances**
3. Wait for Instance state to show **Running** (green dot)
4. Copy the **Public IPv4 address** (e.g. `43.204.143.14`)

---

## PART 2 — Connect to EC2 via SSH

### On Windows (Git Bash)
```bash
# Move key to safe location (only first time)
mkdir -p ~/Downloads
mv ~/Downloads/livekit-key.pem ~/Downloads/livekit-key.pem

# Set correct permissions
chmod 400 ~/Downloads/livekit-key.pem

# Connect to EC2 (type manually — do not copy paste)
ssh -i ~/Downloads/livekit-key.pem ubuntu@43.204.143.14
```

> ⚠️ Replace `43.204.143.14` with your actual EC2 public IP

You will see: `ubuntu@ip-172-31-5-193:~$` — this means you are connected!

---

## PART 3 — Self-Host LiveKit on EC2

### Step 1 — Update the System
```bash
sudo apt update && sudo apt upgrade -y
```

---

### Step 2 — Install Docker
```bash
# Install Docker
sudo apt install docker.io -y

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add ubuntu user to docker group (no sudo needed)
sudo usermod -aG docker ubuntu

# Verify Docker is installed
docker --version
```

---

### Step 3 — Add Swap Memory
> t2.micro only has 1GB RAM. Swap prevents out-of-memory crashes.

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Verify swap is active:
```bash
free -h
```
You should see `1.0G` under Swap.

---

### Step 4 — Create Project Folder
```bash
mkdir -p ~/livekit-project
cd ~/livekit-project
```

---

### Step 5 — Create LiveKit Config File
```bash
nano livekit.yaml
```

Paste this content:
```yaml
port: 7880
rtc:
  port_range_start: 50000
  port_range_end: 50200
  tcp_port: 7881
  use_external_ip: true
redis:
  address: livekit-redis:6379
keys:
  devkey: secret
logging:
  level: info
```

Save: `Ctrl+X` → `Y` → `Enter`

---

### Step 6 — Create SIP Bridge Config File
```bash
# Get your EC2 public IP first
curl -s http://checkip.amazonaws.com
```

```bash
nano sip.yaml
```

Paste this content (replace `YOUR_EC2_PUBLIC_IP` with your actual IP):
```yaml
api_key: devkey
api_secret: secret
ws_url: ws://livekit-server:7880
redis:
  address: livekit-redis:6379
sip_domain: "YOUR_EC2_PUBLIC_IP"
logging:
  level: debug
```

Save: `Ctrl+X` → `Y` → `Enter`

---

### Step 7 — Create Docker Compose File
```bash
nano docker-compose.yml
```

Paste this content:
```yaml
version: "3.8"

services:
  redis:
    image: redis:alpine
    container_name: livekit-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - livekit

  livekit-server:
    image: livekit/livekit-server:latest
    container_name: livekit-server
    command: --config /etc/livekit.yaml
    ports:
      - "7880:7880"
      - "7881:7881"
      - "50000-50200:50000-50200/udp"
    volumes:
      - ./livekit.yaml:/etc/livekit.yaml
    depends_on:
      - redis
    networks:
      - livekit

networks:
  livekit:
    driver: bridge

volumes:
  redis_data:
```

Save: `Ctrl+X` → `Y` → `Enter`

---

### Step 8 — Start Redis + LiveKit Server
```bash
sudo docker compose up -d

# Verify both containers are running
sudo docker ps
```

You should see:
- `livekit-redis` — Up
- `livekit-server` — Up

---

### Step 9 — Start LiveKit SIP Bridge
```bash
sudo docker run -d \
  --name livekit-sip \
  --network livekit-project_livekit \
  -p 5060:5060/udp \
  -p 5060:5060/tcp \
  -p 10000-10100:10000-10100/udp \
  -v ~/livekit-project/sip.yaml:/etc/sip.yaml:ro \
  livekit/sip:latest \
  --config /etc/sip.yaml
```

Verify all 3 are running:
```bash
sudo docker ps
```

You should see 3 containers:
- `livekit-redis` ✅
- `livekit-server` ✅
- `livekit-sip` ✅

---

### Step 10 — Install Python Dependencies
```bash
sudo apt install python3-pip -y

python3 -m pip install \
  livekit \
  livekit-agents \
  livekit-plugins-deepgram \
  livekit-plugins-groq \
  livekit-plugins-silero \
  python-dotenv
```

---

### Step 11 — Create Environment File
```bash
nano .env
```

Paste and fill in your API keys:
```env
# LiveKit (self-hosted)
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# VoBiz SIP Trunk
VOBIZ_SIP_DOMAIN=your_domain.sip.vobiz.ai
VOBIZ_USERNAME=your_username
VOBIZ_PASSWORD=your_password
VOBIZ_OUTBOUND_NUMBER=+91XXXXXXXXXX

# AI Services
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_TTS_MODEL=aura-asteria-en

# TTS Provider
TTS_PROVIDER=deepgram

# Fallback transfer number
DEFAULT_TRANSFER_NUMBER=+91XXXXXXXXXX

# Set after running setup_trunk.py
OUTBOUND_TRUNK_ID=
```

Save: `Ctrl+X` → `Y` → `Enter`

---

### Step 12 — Copy Agent Files from Local PC to EC2

Run these on your **Windows PC Git Bash** (not on EC2):
```bash
scp -i ~/Downloads/livekit-key.pem /c/Users/keert/OneDrive/Desktop/Vobiz+Livekit\(selfhost\)/agent.py ubuntu@43.204.143.14:~/livekit-project/

scp -i ~/Downloads/livekit-key.pem /c/Users/keert/OneDrive/Desktop/Vobiz+Livekit\(selfhost\)/agent_inbound_selfhost.py ubuntu@43.204.143.14:~/livekit-project/

scp -i ~/Downloads/livekit-key.pem /c/Users/keert/OneDrive/Desktop/Vobiz+Livekit\(selfhost\)/setup_trunk.py ubuntu@43.204.143.14:~/livekit-project/

scp -i ~/Downloads/livekit-key.pem /c/Users/keert/OneDrive/Desktop/Vobiz+Livekit\(selfhost\)/setup_inbound_selfhost.py ubuntu@43.204.143.14:~/livekit-project/

scp -i ~/Downloads/livekit-key.pem /c/Users/keert/OneDrive/Desktop/Vobiz+Livekit\(selfhost\)/make_call.py ubuntu@43.204.143.14:~/livekit-project/
```

---

### Step 13 — Register Outbound SIP Trunk (Run ONCE)
```bash
cd ~/livekit-project
python3 setup_trunk.py
```

Copy the printed `ST_xxxxxxxxxx` trunk ID and add it to `.env`:
```bash
nano .env
# Update: OUTBOUND_TRUNK_ID=ST_xxxxxxxxxx
```

---

### Step 14 — Register Inbound SIP Trunk (Run ONCE)
```bash
python3 setup_inbound_selfhost.py
```

Then update VoBiz:
- Go to VoBiz → Inbound Trunks → LiveKit Inbound → Edit
- Set Primary URI to: `YOUR_EC2_PUBLIC_IP:5060`

---

### Step 15 — Start Both Agents
```bash
cd ~/livekit-project

# Start outbound agent
nohup python3 agent.py start > agent.log 2>&1 &

# Wait 3 seconds
sleep 3

# Start inbound agent
nohup python3 agent_inbound_selfhost.py start > inbound.log 2>&1 &

# Verify both are running
sleep 5
echo "=== OUTBOUND ===" && tail -3 agent.log
echo "=== INBOUND ===" && tail -3 inbound.log
```

Both should show: `registered worker` ✅

---

## PART 4 — VoBiz Configuration

### Outbound Trunk Setup
1. Go to VoBiz → Outbound Trunks → Create New
2. Fill in your SIP credentials
3. The trunk ID is automatically registered via `setup_trunk.py`

### Inbound Trunk Setup
1. Go to VoBiz → Inbound Trunks
2. Set **Primary URI**: `YOUR_EC2_PUBLIC_IP:5060`
3. Link your DID number to this trunk
4. Status: **Enabled**

---

## PART 5 — What To Do When EC2 Restarts

> EC2's public IP changes every time you stop and start the instance.

### Step 1 — Get new IP
```bash
curl -s http://checkip.amazonaws.com
```

### Step 2 — Update sip.yaml with new IP
```bash
NEW_IP="x.x.x.x"
sed -i "s/sip_domain: \".*\"/sip_domain: \"$NEW_IP\"/" ~/livekit-project/sip.yaml
```

### Step 3 — Restart SIP bridge
```bash
sudo docker rm -f livekit-sip
sudo docker run -d \
  --name livekit-sip \
  --network livekit-project_livekit \
  -p 5060:5060/udp \
  -p 5060:5060/tcp \
  -p 10000-10100:10000-10100/udp \
  -v ~/livekit-project/sip.yaml:/etc/sip.yaml:ro \
  livekit/sip:latest \
  --config /etc/sip.yaml
```

### Step 4 — Update VoBiz Primary URI
- Go to VoBiz → Inbound Trunks → LiveKit Inbound → Edit
- Change Primary URI to new IP: `NEW_IP:5060`

### Step 5 — Restart agents
```bash
cd ~/livekit-project
pkill -9 -f python3
sleep 3
nohup python3 agent.py start > agent.log 2>&1 &
sleep 3
nohup python3 agent_inbound_selfhost.py start > inbound.log 2>&1 &
```

---

## PART 6 — Useful Commands

```bash
# Check all Docker containers
sudo docker ps

# Check outbound agent logs
tail -f ~/livekit-project/agent.log

# Check inbound agent logs
tail -f ~/livekit-project/inbound.log

# Check memory usage
free -h

# Check disk usage
df -h

# Stop all agents
pkill -9 -f python3

# Restart all Docker containers
sudo docker restart livekit-redis livekit-server livekit-sip
```

---

## PART 7 — Cost Estimate (AWS Free Tier)

| Service | Free Tier | Cost After |
|---------|-----------|------------|
| EC2 t2.micro | 750 hrs/month FREE (1 year) | ~₹600/month |
| EBS Storage (20GB) | 30GB FREE (1 year) | ~₹80/month |
| Data Transfer | 15GB FREE | ₹7/GB |
| Elastic IP | FREE when attached | ₹300/month if unattached |

> 💡 Tip: Use **Elastic IP** to keep the same IP even after restart — saves you from updating VoBiz every time!

---

## PART 8 — How to Add Elastic IP (Fix the changing IP problem)

1. Go to AWS Console → EC2 → **Elastic IPs** (left sidebar)
2. Click **Allocate Elastic IP address**
3. Click **Allocate**
4. Select the new IP → Click **Actions** → **Associate Elastic IP address**
5. Select your `livekit-vobiz` instance
6. Click **Associate**

Now your EC2 will always have the same public IP — no need to update VoBiz or sip.yaml after restart!
