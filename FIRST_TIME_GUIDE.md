# First-Time User Guide
### Pi Cloud CDSS — For Clinicians New to This Kind of Technology

---

> **You don't need to be a developer to run this.**
>
> If you can install an app on your phone, you can get this running. This guide walks you through everything from scratch with no assumptions about prior coding experience.

---

## Start Here — What Is This Actually?

This system is a voice-activated protocol reference that runs on a small computer you can carry in a cargo pocket.

You ask it a clinical question. It searches your protocol library and either displays or reads you the relevant guidance. That's the core of it. Everything in this guide is just the one-time setup to make that work.

The system is a research prototype — not a finished product and not approved for patient care. It exists to explore whether lightweight AI tools can reduce cognitive load in austere environments. If you're here, you're part of that evaluation.

---

## The Pieces and Why They Exist

| Piece | What It Is | Why You Need It |
|---|---|---|
| **Python** | Programming language | The system is written in it |
| **Git** | Version control tool | How you download and update the code |
| **GitHub** | Website for storing code | Where the code lives |
| **Virtual Environment** | Isolated Python workspace | Keeps this project's dependencies separate |
| **Raspberry Pi** | Small field computer | Runs the voice interface in the field |
| **Cloud VM** | Rented internet computer | Stores and searches your protocol library |
| **Claude or GPT API** | AI service | Reads protocols and summarizes them |
| **ElevenLabs** | Text-to-speech service | Speaks responses through your headset |
| **.env file** | Private config file | Stores your API keys securely on your computer |

You don't need to understand all of these deeply. You just need to get each one set up once.

---

## Section 1 — Getting the Code

### What is GitHub?

GitHub is where developers store and share code — like Google Drive for software. The CDSS code lives there and you download it from there. You won't need to understand much about it beyond the two commands below.

### Install Git

**Mac:** Open Terminal (search "Terminal" in Spotlight) and run:
```bash
git --version
```
If Git isn't installed, Mac will prompt you to install it automatically.

**Windows:** Download from [git-scm.com](https://git-scm.com) and install. All defaults are fine. Then open **Git Bash** from your Start menu instead of Command Prompt.

**Raspberry Pi / Linux:**
```bash
sudo apt install git -y
```

### Download the Code

```bash
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss
```

You now have all the code on your computer.

### Update the Code Anytime

```bash
cd pi-cloud-cdss
git pull
```

---

## Section 2 — Python Setup

### Install Python

Go to [python.org/downloads](https://python.org/downloads) and download Python 3.10 or newer.

On Windows: during installation, check **"Add Python to PATH"** — this is important.

Verify it worked:
```bash
python3 --version
# Should show: Python 3.10.x or newer
```

### Create a Virtual Environment

A virtual environment is an isolated workspace for this project. It keeps dependencies for this project separate from everything else on your computer. You only create it once.

```bash
# Inside the pi-cloud-cdss folder
python3 -m venv venv
```

**Activate it** — do this every time you open a new terminal to work on the project:
```bash
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

You'll see `(venv)` at the start of your terminal line when it's active.

### Install Dependencies

```bash
pip install -r requirements.txt
```

This installs everything the system needs. Takes a few minutes the first time.

---

## Section 3 — API Accounts

An API key is a private password that lets your code access a service like Claude or ElevenLabs. It also tracks your usage for billing. Keep it private — treat it like a password.

### Anthropic Claude (Recommended AI)

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an account and add a payment method
3. Go to **API Keys** → **Create Key** → name it `CDSS`
4. Copy the key immediately — it starts with `sk-ant-`
5. You cannot view it again after closing the page — save it somewhere secure

**Cost:** Roughly $0.001–0.002 per clinical query. $5 in credit lasts hundreds of queries during testing.

### OpenAI GPT (Alternative AI)

1. Go to [platform.openai.com](https://platform.openai.com)
2. Create an account and add a payment method
3. Go to **API Keys** → **Create new secret key** → name it `CDSS`
4. Copy the key — starts with `sk-`

**Cost:** Similar to Claude at the mini model tier.

> You can configure both and switch between them with one line change. No code modification needed.

### ElevenLabs (Voice Output)

1. Go to [elevenlabs.io](https://elevenlabs.io)
2. Create a free account — no credit card needed to start
3. Go to **Profile** → copy your **API Key**
4. Go to **Voices** → **Voice Library** → find **Adam** or **Rachel** → **Add to My Voices**
5. Click your chosen voice → copy the **Voice ID**

**Free tier:** 10,000 characters/month — sufficient for initial evaluation.

---

## Section 4 — Configuration

Your API keys are stored in a file called `.env` in the project folder. This file never gets shared to GitHub — it lives on your computer only.

```bash
# Create your config file from the template
cp .env.example .env

# Open it to edit
nano .env                       # Mac/Linux terminal
notepad .env                    # Windows
```

Fill in your keys:

```bash
# Which AI to use — change this one line to switch
AI_BACKEND=claude               # or: openai

ANTHROPIC_API_KEY=sk-ant-your-key-here
ANTHROPIC_MODEL=claude-sonnet-4-6

OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-5.4-mini

ELEVENLABS_API_KEY=your-key-here
ELEVENLABS_VOICE_ID=your-voice-id-here

CLOUD_API_URL=http://your-vm-ip:8000
```

Save and close. That's your configuration.

### Switching Between Claude and GPT

One line in `.env`:
```bash
AI_BACKEND=claude    # Use Claude
AI_BACKEND=openai    # Use GPT
```

Restart the client after changing it.

---

## Section 5 — Running the System

```bash
# Activate your environment (if not already active)
source venv/bin/activate

# Run
python client.py
```

You'll see a startup banner showing which AI backend is active. At the prompt:

- Type any clinical question and press Enter
- Type `test` to verify your API connections
- Type `switch` to see how to change backends
- Type `quit` to exit

### Example Queries to Try

```
Management of tension pneumothorax in the field
RSI protocol for 90kg burn patient
TXA dosing — patient approximately 80 kilograms
MARCH protocol for blast injury with 2 hour ETOC
Pediatric airway — patient approximately 20 kilograms
```

---

## Frequently Asked Questions

**Do I need to know how to code?**
No. Once set up, you type questions and read or hear answers. The setup is a one-time process this guide covers completely.

**Is this safe to use for patient care?**
No — and this matters. This is a research prototype for training, simulation, and evaluation only. It is not FDA approved, not clinically validated, and not a substitute for your training and protocols. Treat it like a study tool.

**What does it cost?**
API costs are very low for testing — expect to spend $1–5 during initial evaluation. ElevenLabs has a free tier. The cloud VM (~$30–50/month on Google Cloud) is only needed for the full RAG pipeline. Without a VM, the system still works using AI knowledge alone, just without protocol-specific retrieval.

**Can I use my own agency's protocols?**
Yes — that's a core design goal. Place your PDFs in `data/protocols/` and run the ingestion script. Works with any PDF-based protocol library.

**What if the voice recognition doesn't work well?**
Switch to text mode — type your question instead of speaking it. Text mode is fully functional and avoids all audio hardware issues. It's also more reliable in noisy environments.

**Something broke — what do I do?**
Open an issue at the GitHub repository. Include what you were doing, what you expected, and what happened. Screenshots help.

**I used this for training — now what?**
Please reach out to azelton@proton.me. Feedback from clinicians in the field is the most valuable input this project can receive and directly shapes the next version.

---

## Free Learning Resources

If this sparked interest in learning more — here are honest recommendations, all free.

### Python

| Resource | Why |
|---|---|
| [CS50P — Harvard](https://cs50.harvard.edu/python/) | Best free Python course available. Genuinely excellent. |
| [Automate the Boring Stuff](https://automatetheboringstuff.com) | Free book written for non-programmers, practical focus |
| [Python.org Beginner's Guide](https://wiki.python.org/moin/BeginnersGuide) | Official, no fluff |

### Git and GitHub

| Resource | Why |
|---|---|
| [GitHub Skills](https://skills.github.com) | Interactive, browser-based, no setup required |
| [Oh My Git!](https://ohmygit.org) | A game that teaches Git — genuinely fun |
| [Pro Git Book](https://git-scm.com/book/en/v2) | Free, comprehensive reference |

### AI and How It Works

| Resource | Why |
|---|---|
| [Andrej Karpathy — Neural Networks Zero to Hero](https://karpathy.ai/zero-to-hero.html) | Best explanation of how LLMs actually work |
| [Fast.ai](https://fast.ai) | Practical ML for people who want to build things |
| [Hugging Face Course](https://huggingface.co/learn) | Free, covers transformers and NLP hands-on |

### Command Line

| Resource | Why |
|---|---|
| [The Missing Semester — MIT](https://missing.csail.mit.edu) | Everything they don't teach in school |
| [Command Line Crash Course](https://learnpythonthehardway.org/book/appendixa.html) | 15 minutes, covers the basics |

### Raspberry Pi

| Resource | Why |
|---|---|
| [Raspberry Pi Official Docs](https://www.raspberrypi.com/documentation/) | Comprehensive, well maintained |
| [Jeff Geerling YouTube](https://www.youtube.com/@JeffGeerling) | Best Pi content on YouTube |

---

## Glossary

| Term | Plain English |
|---|---|
| **API** | A way for two programs to talk to each other |
| **API Key** | A private password for accessing an AI service |
| **Terminal** | A text-based way to control your computer |
| **Python** | The programming language this system is written in |
| **Git** | A tool that tracks changes to code |
| **GitHub** | A website for storing and sharing code |
| **Virtual Environment** | An isolated Python workspace for one project |
| **pip** | Python's package installer |
| **.env file** | A local file storing private configuration |
| **RAG** | Retrieval-Augmented Generation — searching a document library before generating an AI response |
| **LLM** | Large Language Model — the AI engine (Claude, GPT, etc.) |
| **ChromaDB** | The vector database storing your indexed protocol library |
| **VM** | Virtual Machine — a rented computer in the cloud |
| **SSH** | A secure way to connect to a remote computer |
| **WireGuard** | An encrypted VPN tunnel |

---

*Part of the Pi Cloud CDSS project — [AI-in-Austere-Medicine-Project](https://github.com/AI-in-Austere-Medicine-Project)*  
*Questions or feedback: azelton@proton.me*

