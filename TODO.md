# EdgeCDSS Development Roadmap

## IN PROGRESS
- TTS medical term expansion tuning (ongoing)

## UP NEXT — HIGH PRIORITY

### 1. Speed Optimization (Target: <5 second response)
- [ ] Switch LLM to faster model variant (gpt-4o-mini or claude-haiku)
- [ ] Implement ElevenLabs streaming TTS — speak while generating
- [ ] Reduce max_tokens to 150-200 for voice/brief mode
- [ ] Profile full request cycle — identify biggest latency bottleneck
- [ ] Target: ChromaDB <1s, LLM <3s, TTS streaming <1s

### 2. Voice Interrupt
- [ ] Run audio playback in separate thread
- [ ] Main thread listens for keyboard or wake word during playback
- [ ] Kill audio thread on new input, process new query immediately
- [ ] Implement wake word detection (OpenWakeWord)

### 3. Auto-Update Boot System
- [ ] Create boot_script.sh — git pull latest then run cdss_client.py
- [ ] Configure systemd service to run boot script on startup
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
- [ ] Configure WireGuard server to route local subnet to VPN clients
- [ ] Add edge devices as WireGuard peers with static VPN IPs
- [ ] Test SSH to edge devices through WireGuard from any network
- [ ] Document multi-device network architecture
- [ ] Implement split tunneling — local traffic stays local

### 6. Austere Environment Deployment
- [ ] Load and process additional national/regional medical protocol sets
- [ ] Migrate to higher-performance edge hardware for larger knowledge bases
- [ ] Optimize ChromaDB chunking for expanded protocol volumes
- [ ] Test on satellite connectivity tiers (broadband and narrowband)
- [ ] Validate tiered degradation: broadband → narrowband → offline
- [ ] Solar/battery power budget validation for full system

## INFRASTRUCTURE

### Cloud Backend Cleanup
- [ ] Decommission legacy VM after confirming new backend stable
- [ ] Monitor and right-size cloud VM based on usage patterns
- [ ] Automated backup of ChromaDB index to cloud storage
- [ ] Configure billing alerts and cost monitoring

### Multi-Provider LLM Support
- [ ] Verify Claude API integration on backend
- [ ] Build provider toggle — switch OpenAI/Claude per request
- [ ] Compare response quality across providers for medical queries
- [ ] Cost-per-query analysis across providers

### Security Hardening
- [ ] Add API key authentication to backend endpoints
- [ ] Generate device-specific API tokens per edge deployment
- [ ] Rate limiting on /query endpoint
- [ ] VPN tunnel between cloud backend and edge devices

### Protocol Expansion
- [ ] Pipeline for ingesting new protocol sets (national, regional, specialty)
- [ ] Chunking strategy optimization for non-JTS formatted documents
- [ ] Multi-language protocol support evaluation
- [ ] Version control for protocol knowledge base updates

## COMPLETED
- [x] EdgeCDSS-Nano: Raspberry Pi 4 baseline deployment
- [x] FastAPI cloud backend with ChromaDB vector database
- [x] JTS CPG knowledge base — 89 protocols indexed
- [x] Voice interface — wake word detection + ElevenLabs TTS
- [x] Radxa Zero 3W thin client deployment
- [x] Cloud backend migration to new VM
- [x] cdss_client.py — thin client routing queries to cloud backend
- [x] TTS medical term expansion — acronyms, units, concentrations
- [x] Tiered connectivity architecture designed
- [x] GitHub organization established