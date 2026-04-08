# Pi Cloud CDSS — Clinical Decision Support System
### AI-Powered Medical Protocol Assistant for Austere & Resource-Limited Environments

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Status: Research Prototype](https://img.shields.io/badge/status-research%20prototype-orange.svg)]()

---

## ⚠️ MEDICAL DISCLAIMER — READ FIRST

> **THIS IS A RESEARCH AND EDUCATIONAL TOOL — NOT FOR CLINICAL USE**
>
> ❌ NOT intended for actual patient care decisions  
> ❌ NOT FDA approved or clinically validated  
> ❌ NOT a replacement for medical training or qualified professionals  
> ✅ FOR research, education, training simulation, and field evaluation ONLY  
>
> **Always follow your agency's protocols and consult qualified medical personnel for patient care.**

---

## What Is This? (For Medics)

Imagine having a highly knowledgeable partner in the field who has read every medical protocol your agency uses — and can answer your questions out loud, hands-free, in plain English.

That's what this system does. You press a button, ask a clinical question ("RSI protocol for a 90kg burn patient"), and within seconds you hear a spoken response based on your protocol library — whether that's JTS Clinical Practice Guidelines, your agency's EMS protocols, or any PDF-based guidelines you load in.

It runs on a small Raspberry Pi device you can carry in a cargo pocket, connects to cloud AI for processing, and speaks responses through a Bluetooth headset or speaker. When connectivity is limited, it can operate on cached protocols.

**Designed for:**
- Tactical and austere medicine
- Wilderness and remote EMS
- Disaster response and mobile medical units
- Medical training and simulation
- Protocol familiarization

---

## What Is This? (For Developers)

A hybrid cloud-edge clinical decision support system built on:

- **Edge device:** Raspberry Pi Zero 2W (client) with GPIO PTT handling, Whisper STT, voice I/O
- **Cloud backend:** Google Cloud VM running FastAPI + ChromaDB vector database
- **LLM:** Interchangeable — OpenAI GPT-4, Anthropic Claude, or local models
- **TTS:** ElevenLabs (primary), OpenAI TTS, or pyttsx3 (offline fallback)
- **Connectivity:** WireGuard VPN tunnel, Starlink Mini, GL.iNet Beryl AX field repeater
- **Protocol ingestion:** Any PDF-based medical guidelines → ChromaDB → RAG pipeline

The architecture is intentionally modular. Swap the LLM backend, the TTS engine, or the protocol database without touching the core query pipeline.

---

## Key Features

| Feature | Details |
|---|---|
| 🎤 Voice Input | Hands-free PTT button or USB mic |
| 🔊 Natural Speech Output | ElevenLabs, OpenAI TTS, or offline fallback |
| 🤖 Dual AI Backend | Switch between Claude and GPT-4 via single config toggle |
| ☁️ Cloud Processing | FastAPI + ChromaDB vector search |
| 📚 Protocol Agnostic | Works with ANY PDF-based medical guidelines |
| 📴 Offline Capable | Critical protocols cached locally |
| ⚡ Fast Response | 6–13 seconds end-to-end |
| 🔒 Field Security | WireGuard encrypted tunnel |
| 🌐 Starlink Ready | Tested with Starlink Mini + GL.iNet repeater |

---

## Hardware Requirements

### Minimum
- Raspberry Pi Zero 2W (or Pi 3/4)
- USB microphone OR Bluetooth headset with HSP/HFP profile
- Internet connection (WiFi, cellular, or Starlink)

### Recommended Field Kit
- Raspberry Pi Zero 2W
- PTT button (GPIO connected)
- Shokz OpenRun Pro or similar bone conduction headset
- 18650 battery pack
- GL.iNet Beryl AX (GL-MT3000) WiFi repeater
- Starlink Mini for connectivity

### Cloud Backend
- Google Cloud VM (e2-medium or equivalent — ~$30–50/month)
- OR self-hosted Linux server

---

## API Accounts You'll Need

You need at least one AI account and one TTS account. All are free to sign up — you pay for usage.

### AI Backend (Choose One or Both)

**Option A — Anthropic Claude** *(Recommended)*
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an account and add a payment method
3. Navigate to **API Keys** → **Create Key**
4. Copy your key — starts with `sk-ant-`
5. Costs approximately $0.003–0.015 per query

**Option B — OpenAI GPT-4**
1. Go to [platform.openai.com](https://platform.openai.com)
2. Create an account and add a payment method
3. Navigate to **API Keys** → **Create new secret key**
4. Copy your key — starts with `sk-`
5. Costs approximately $0.01–0.03 per query

> You can configure both and switch between them with a single line in your `.env` file.

### Text-to-Speech — ElevenLabs *(Recommended)*

ElevenLabs produces the most natural-sounding medical voice output — important for field use where clarity matters.

1. Go to [elevenlabs.io](https://elevenlabs.io)
2. Create a free account (10,000 characters/month free tier)
3. Navigate to **Profile** → **API Key**
4. Copy your key
5. Choose a voice in the ElevenLabs dashboard — **"Adam"** or **"Rachel"** work well for clinical clarity

> Free tier is enough for testing. Paid plans start at $5/month for field deployment.

---

## Installation

### Step 1 — Clone the Repository

```bash
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss
```

### Step 2 — Create Python Environment

```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# OR
venv\Scripts\activate           # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3 — Configure Your API Keys

Copy the environment template:

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```bash
# AI Backend — choose Claude or OpenAI
AI_BACKEND=claude               # Options: "claude" or "openai"

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-your-key-here

# OpenAI (if using GPT-4)
OPENAI_API_KEY=sk-your-key-here

# ElevenLabs TTS
ELEVENLABS_API_KEY=your-key-here
ELEVENLABS_VOICE_ID=your-voice-id-here

# Cloud VM endpoint
CLOUD_API_URL=http://your-vm-ip:8000
```

> **IMPORTANT:** Never share your `.env` file. It is excluded from Git by `.gitignore` automatically.

### Step 4 — Switching Between Claude and OpenAI

It's one line in your `.env`:

```bash
AI_BACKEND=claude    # Use Anthropic Claude
AI_BACKEND=openai    # Use OpenAI GPT-4
```

No code changes needed. The client reads this at startup and routes accordingly.

### Step 5 — Load Your Protocol Library

Place your protocol PDFs in `data/protocols/` and run:

```bash
python scripts/ingest_pdfs.py
```

This indexes all documents into ChromaDB for vector search. Works with:
- JTS Clinical Practice Guidelines
- NAEMSP / PHTLS protocols
- Agency EMS protocols
- Any PDF-based medical guidelines

---

## Usage

### Voice Mode (Field Use)

```bash
source venv/bin/activate
python client.py --mode voice
```

- Press PTT button (or press Enter) to speak
- Ask your clinical question clearly
- Hear the response spoken through your headset

### Text Mode (Testing / Training)

```bash
python client.py --mode text
```

Type your question and receive a text response. Useful for testing without audio hardware.

### Example Queries

```
"Management of tension pneumothorax in the field"
"RSI protocol for 90kg burn patient"
"TXA dosing — patient is approximately 80 kilograms"
"Tourniquet application steps"
"Hemorrhagic shock — MARCH protocol"
"Pediatric airway — patient is approximately 20 kilograms"
```

---

## System Architecture

```
┌─────────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│  Raspberry Pi Zero  │         │   Google Cloud VM    │         │   AI Backend    │
│  (Edge Device)      │         │   (Cloud Backend)    │         │                 │
│                     │         │                      │         │  Claude (Ant.)  │
│  • PTT Button       │──WG──▶  │  • FastAPI Server    │──────▶  │       OR        │
│  • Whisper STT      │  VPN    │  • ChromaDB Vector   │         │  GPT-4 (OAI)   │
│  • ElevenLabs TTS   │◀────────│  • Protocol RAG      │◀────────│                 │
│  • Local Cache      │         │  • Query Pipeline    │         └─────────────────┘
└─────────────────────┘         └──────────────────────┘
      Edge Device                   Cloud Backend                    AI Services

       ▲
       │ Starlink Mini
       │ + GL.iNet Beryl AX
       │ (Field Connectivity)
```

---

## ElevenLabs Voice Setup

For best results in the field:

1. Log into [elevenlabs.io](https://elevenlabs.io)
2. Go to **Voices** → **Voice Library**
3. Recommended voices for clinical use:
   - **Adam** — clear, authoritative male
   - **Rachel** — calm, professional female
   - **Charlie** — natural conversational
4. Click **Add to My Voices** on your chosen voice
5. Go to **Profile** → copy your **Voice ID**
6. Paste Voice ID into your `.env` as `ELEVENLABS_VOICE_ID`

---

## Security Notes

- **Never commit your `.env` file** — it's excluded by `.gitignore` but double-check before pushing
- **Use `.env.example`** to share configuration structure without exposing keys
- **Rotate API keys** immediately if accidentally exposed
- **WireGuard tunnel** encrypts all traffic between Pi and cloud VM
- **Firewall your VM** — restrict inbound to port 8000 from your WireGuard subnet only

---

## Troubleshooting

**No audio output:**
```bash
aplay -l                    # List audio devices
speaker-test -t wav -c 2   # Test speakers
```

**Microphone not detected:**
```bash
arecord -l                  # List recording devices
arecord -d 3 test.wav       # Record 3 second test
aplay test.wav              # Play it back
```

**Cannot reach cloud VM:**
```bash
curl http://YOUR_VM_IP:8000/health    # Test VM connectivity
```

**API errors:**
- Verify your key is correct in `.env`
- Check you have credits/billing set up on your API account
- Claude: check [status.anthropic.com](https://status.anthropic.com)
- OpenAI: check [status.openai.com](https://status.openai.com)

---

## Performance

| Metric | Value |
|---|---|
| Voice recognition accuracy | 90%+ (clear speech) |
| End-to-end response time | 6–13 seconds |
| Protocol coverage (JTS) | 89 Clinical Practice Guidelines |
| Database size | 7,186+ indexed document chunks |
| Offline cache | Critical protocols available without connectivity |

---

## License

**Creative Commons Attribution 4.0 International (CC BY 4.0)**

✅ Free to use, modify, and share — including commercially  
✅ Attribution required — credit the original author  
✅ Research, education, and field evaluation encouraged  

See [LICENSE](LICENSE) for full terms.

---

## Contributing

Contributions welcome — especially from medics, paramedics, and field medicine practitioners who can help validate clinical query responses and improve the interface for field use.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## Acknowledgments

- **Joint Trauma System (JTS)** — Clinical Practice Guidelines
- **Anthropic** — Claude AI API
- **OpenAI** — GPT-4 API and TTS
- **ElevenLabs** — Natural voice synthesis
- **CoROM (College of Remote and Offshore Medicine)** — Research support
- Medical professionals and medics who provided field feedback

---

## Author

**Andrew Azelton, BS, NRP, LP, FP-C, WP-C**  
MSc Candidate, Austere Critical Care (CoROM)  
Founder, Arcane Knowledge Group (AKG)

GitHub: [@aazelton](https://github.com/aazelton)  
Organization: [AI-in-Austere-Medicine-Project](https://github.com/AI-in-Austere-Medicine-Project)

---

*Version 2.0 | 2026 | Research Prototype — Not for Clinical Use*
