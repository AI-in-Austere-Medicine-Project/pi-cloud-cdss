# First-Time User Guide
### EdgeCDSS 4.0 — For Clinicians New to This Kind of Technology

---

> **You don't need to install anything to try this.**
>
> EdgeCDSS 4.0 runs in your web browser. If you can open a webpage, you can evaluate this system in the next sixty seconds. Everything past Path 1 in this guide is optional.

---

## Start Here — What Is This Actually?

EdgeCDSS is a clinical decision support system for austere and prolonged field care. You describe a casualty in ordinary field language — *"80kg male, blast injury, severe pain, IV access"* — and it answers in seconds with structured guidance: what to do, exact volumes to draw, what to watch, what never to give, cited to the Joint Trauma System Clinical Practice Guidelines it retrieved the answer from.

The entire system runs on a computer the size of a paperback (an NVIDIA Jetson Orin Nano) and reaches you through an encrypted tunnel. There is no cloud server. The knowledge base — 89 JTS CPGs — lives on the device itself.

The system is a research prototype — not a finished product and not approved for patient care. It exists to explore whether guideline-grounded AI tools can reduce cognitive load in austere environments. If you're here, you're part of that evaluation. **Use simulated scenarios only — never real patient information.**

---

## Path 1 — Use the Web Portal (60 seconds, nothing to install)

1. Open **https://cdss.arcanekg.com** on any device — phone, tablet, laptop.
2. The access token is already filled in. Type a scenario in the box.
3. Read the response. Note the **validator badge**, the **source citations** (protocol + page), and the response time.
4. Tap **🔊 listen** to hear it spoken (useful hands-free).

### Example scenarios to try

```
80kg male, blast injury to the leg, severe pain, IV access — what can I give?
Need RSI meds for a 100kg male with facial burns. Give me doses.
When do I convert a tourniquet to a pressure dressing in prolonged field care?
40% TBSA burns on an 80kg male — fluid rate for the first 24 hours?
22kg child, femur fracture, IO access. Ketamine dose for pain?
```

Notice what it does when you *don't* give it enough: ask for a pediatric dose without a weight and it will refuse to dose until you provide one. That refusal is the safety architecture working.

### Give feedback — this is the whole point

Every response has two buttons:

- **✓ clinically appropriate** — one tap, you're done.
- **⚠ flag issue** — opens a short clinical report: severity (minor / significant / dangerous-if-followed), what kind of problem, and what it *should* have said. Cite the protocol if you can.

Flagged responses are reproduced from audit logs and fixed with regression tests. A field flag has turned into a same-day fix more than once. Your clinical judgment is the most valuable input this project receives.

---

## Path 2 — Run Your Own Server (for the technically curious)

Everything in Path 1 is served by one Python application you can run yourself — on a Jetson, a Linux box, or a Mac. Your own instance, your own guideline library.

### The pieces and why they exist

| Piece | What It Is | Why You Need It |
|---|---|---|
| **Python** | Programming language | The system is written in it |
| **Git / GitHub** | Code download tools | Where the code lives and how you get it |
| **Virtual environment** | Isolated Python workspace | Keeps this project's dependencies separate |
| **OpenAI API key** | AI service credential | Powers language generation and validation |
| **ChromaDB** | Local search database | Stores and searches your guideline library on-device |
| **.env file** | Private config file | Stores your API keys — never shared to GitHub |

### Setup

```bash
# 1. Get the code
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss

# 2. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-server.txt

# 3. Configure — create server/.env with your keys
cp .env.example server/.env
nano server/.env       # add OPENAI_API_KEY and a CDSS_ACCESS_TOKEN of your choosing

# 4. Run
cd server
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 in a browser — that's your own portal.

Your server starts with an **empty knowledge base** ("documents: 0" on the health check). Load it with any PDF protocol library:

```bash
python ingest_jts.py --pdf-dir ./data/your_protocols
python build_protocol_index.py     # builds the clinical router index
```

**Getting an OpenAI API key:** create an account at [platform.openai.com](https://platform.openai.com), add a payment method, then API Keys → Create. Copy it immediately — it's shown once. Cost is roughly $0.001 per query at the model tier this project uses; $5 lasts a long evaluation.

**Optional voice output:** add `ELEVENLABS_API_KEY` from [elevenlabs.io](https://elevenlabs.io) (free tier: 10,000 characters/month). Without it, the 🔊 button reports audio unavailable and everything else works normally.

**Deploying on a Jetson Orin Nano:** run `bash jetson_cdss_setup_v2.sh` — it installs packages, builds the environment, and registers the server as a system service that starts on boot.

---

## Path 3 — The Voice Client (edge devices)

`client/cdss_client.py` is a voice interface for small field devices (Radxa Zero, Raspberry Pi): push-to-talk in, spoken response out, pointed at any EdgeCDSS server. It has its own dependencies (`pip install -r client/requirements.txt`) and reads the server URL and token from `.env`. It is under active development — check `TODO.md` for current status before relying on it.

---

## Frequently Asked Questions

**Do I need to know how to code?**
No. Path 1 is a webpage. Paths 2–3 are copy-paste terminal commands this guide covers completely.

**Is this safe to use for patient care?**
No — and this matters. Research prototype, for training, simulation, and evaluation only. Not FDA approved, not clinically validated, not a substitute for your training and protocols. Never enter real patient information.

**What does it cost?**
Path 1: nothing. Path 2: API costs of roughly $1–5 across an entire evaluation; there is no cloud server to rent. The reference hardware (Jetson Orin Nano) is ~$249 one-time.

**Can I use my own agency's protocols?**
Yes — that's a core design goal. Point `ingest_jts.py` at a folder of your protocol PDFs and the system builds its knowledge base from them. Works with any PDF-based library.

**Why did it refuse to answer / ask me for more information?**
By design. The system will not dose a pediatric patient without a confirmed weight, will not calculate from estimated weights, and blocks contraindicated requests outright. If a refusal seems clinically wrong, flag it — wrongful blocks are treated as bugs and fixed.

**Something broke — what do I do?**
Open an issue at the GitHub repository with what you did, what you expected, and what happened. Screenshots help.

**I tested it — now what?**
Use the in-interface feedback buttons, and/or reach out: azelton@proton.me. Feedback from clinicians is the most valuable input this project receives and directly shapes the next version.

---

## Free Learning Resources

If this sparked interest in learning more — honest recommendations, all free.

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

### Edge Hardware

| Resource | Why |
|---|---|
| [NVIDIA Jetson documentation](https://developer.nvidia.com/embedded/jetson-developer-kits) | The reference platform for this project |
| [JetsonHacks](https://jetsonhacks.com) | Practical Jetson guides and setup walkthroughs |
| [Jeff Geerling YouTube](https://www.youtube.com/@JeffGeerling) | Best small-computer content on YouTube |

---

## Glossary

| Term | Plain English |
|---|---|
| **API** | A way for two programs to talk to each other |
| **API Key** | A private password for accessing an AI service |
| **Terminal** | A text-based way to control your computer |
| **Virtual Environment** | An isolated Python workspace for one project |
| **.env file** | A local file storing private configuration |
| **RAG** | Retrieval-Augmented Generation — searching a document library before generating an AI response |
| **LLM** | Large Language Model — the AI engine used for language generation |
| **ChromaDB** | The database storing your indexed protocol library |
| **Embedding** | A numerical fingerprint of meaning, used for semantic search |
| **Deterministic** | Computed by ordinary code with one right answer — not by AI |
| **Jetson Orin Nano** | The small NVIDIA computer the reference system runs on |
| **Cloudflare Tunnel** | An outbound-only encrypted connection that makes the device reachable without opening ports |
| **Fail-closed** | When in doubt, refuse — the system blocks rather than guesses |

---

*Part of the AI in Austere Medicine Project — [GitHub](https://github.com/AI-in-Austere-Medicine-Project) · [Project site](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/) · [Substack](https://aiamp.substack.com)*
*Questions or feedback: azelton@proton.me*
