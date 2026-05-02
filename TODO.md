# EdgeCDSS Development Roadmap

## IN PROGRESS
- TTS medical term expansion tuning (ongoing)
- Response format refinement — JTS vs non-JTS dual format (ongoing)

## UP NEXT — HIGH PRIORITY

### 1. Speed Optimization (Target: <5 second response)
- [ ] Switch LLM to faster model variant (gpt-4o-mini or claude-haiku)
- [ ] Implement ElevenLabs streaming TTS — speak while generating
- [ ] Reduce max_tokens to 150-200 for voice/brief mode
- [ ] Profile full request cycle — identify biggest latency bottleneck
- [ ] Target: ChromaDB <1s, LLM <3s, TTS streaming <1s

### 2. Voice Interrupt
- [ ] Run audio playback in separate thread ✓ (async implemented)
- [ ] Main thread listens for keyboard or wake word during playback
- [ ] Kill audio thread on new input, process new query immediately
- [ ] Implement wake word detection (OpenWakeWord)

### 3. Auto-Update Boot System
- [ ] Create boot_script.sh — git pull latest then run cdss_client.py ✓
- [ ] Configure systemd service to run boot script on startup ✓
- [ ] Configure wpa_supplicant for multi-network WiFi auto-connect
- [ ] Implement reverse SSH tunnel for remote device management
- [ ] Test full boot-to-running sequence headless (no keyboard/monitor)

### 4. Lightweight Client Build (Pi Zero 2W)
- [ ] Validate Pi Zero 2W with wired mic and headphones
- [ ] Build deployable image — flash, boot, auto-connect, auto-update, run
- [ ] Document setup process for non-technical users
- [ ] Test wired audio stack (ALSA/PulseAudio) on Pi Zero 2W
- [ ] Benchmark latency vs Radxa Zero 3W

### 5. Network Mesh & VPN
- [ ] Configure WireGuard server (HP EliteDesk) to route 192.168.68.0/24 subnet to VPN clients
- [ ] Add Radxa and edge devices as WireGuard peers with static VPN IPs
- [ ] Test SSH to edge devices through WireGuard from any network
- [ ] Document multi-device network architecture
- [ ] Implement split tunneling — local traffic stays local, cloud through VPN

### 6. Austere Environment Deployment
- [ ] Load and process additional national/regional medical protocol sets
- [ ] Migrate to higher-performance edge hardware for larger knowledge bases
- [ ] Optimize ChromaDB chunking for expanded protocol volumes
- [ ] Test on satellite connectivity tiers (broadband and narrowband)
- [ ] Validate tiered degradation: broadband → narrowband → offline
- [ ] Solar/battery power budget validation for full system

## INFRASTRUCTURE

### Repository Consolidation
- [ ] Create server/ directory in pi-cloud-cdss repo
- [ ] Copy cdss-cloud backend files into server/ folder (main.py, openai_client.py, embeddings.py, scripts/)
- [ ] Add server-specific requirements.txt
- [ ] Verify .gitignore excludes .env, cache/, data/, venv/, *.log
- [ ] Push unified repo structure to GitHub
- [ ] Update arcaneone deployment to pull from unified repo
- [ ] Single repo contains: thin client + backend + boot scripts + docs

### Cloud Backend Cleanup
- [ ] Decommission mistral-vm after confirming arcaneone stable
- [ ] Set arcaneone external IP to Static (currently ephemeral — changes on restart)
- [ ] Monitor and right-size cloud VM based on usage patterns
- [ ] Automated backup of ChromaDB index to cloud storage
- [ ] Configure billing alerts and cost monitoring

### Multi-Provider LLM Support
- [ ] Verify Claude API integration on arcaneone backend
- [ ] Build provider toggle — switch OpenAI/Claude per request
- [ ] Compare response quality across providers for medical queries
- [ ] Cost-per-query analysis across providers

### Security Hardening
- [ ] Add API key authentication to backend endpoints (currently open on port 8000)
- [ ] Generate device-specific API tokens per edge deployment
- [ ] Rate limiting on /query endpoint
- [ ] VPN tunnel between cloud backend and edge devices

### Protocol Expansion
- [ ] Pipeline for ingesting new protocol sets (national, regional, specialty)
- [ ] Chunking strategy optimization for non-JTS formatted documents
- [ ] Multi-language protocol support evaluation
- [ ] Version control for protocol knowledge base updates

### Android / Termux Client
- [ ] Resolve pydantic-core ARM64 build failure on Termux
- [ ] Implement Termux TTS fallback (termux-tts-speak) instead of ElevenLabs
- [ ] Test full cdss_client.py on Android via Termux
- [ ] Validate audio output via Termux:API

## COMPLETED
- [x] EdgeCDSS-Nano: Raspberry Pi 4 baseline deployment
- [x] FastAPI cloud backend with ChromaDB vector database
- [x] JTS CPG knowledge base — 89 protocols indexed
- [x] Voice interface — ElevenLabs TTS with medical term expansion
- [x] Radxa Zero 3W thin client deployment
- [x] Cloud backend migration from mistral-vm to arcaneone (e2-medium)
- [x] cdss_client.py — thin client routing queries to arcaneone backend
- [x] TTS medical term expansion — acronyms, units, concentrations
- [x] Number-attached unit pronunciation fixed (500mg → 500 milligrams)
- [x] lbs to kg auto-conversion for patient safety
- [x] Non-blocking async TTS — prompt returns immediately after response
- [x] Pygame output suppressed, audio timeout added
- [x] Dual response format — JTS structured vs non-JTS concise
- [x] Zero math rule — all dosing resolved to final mL, no provider math
- [x] TLDR section added to all responses
- [x] .gitignore protecting API keys, IPs, and large data files
- [x] Auto-update boot script with network fallback
- [x] Systemd service for auto-launch on boot
- [x] Tiered connectivity architecture documented (Starlink/BGAN/Iridium/Offline)
- [x] GitHub organization established — AI-in-Austere-Medicine-Project
- [x] EdgeCDSS system architecture PDF generated
- [x] Development roadmap published to GitHub