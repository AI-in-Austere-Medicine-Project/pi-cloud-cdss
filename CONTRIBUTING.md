# Contributing to EdgeCDSS

EdgeCDSS is an open research project. All contributions are welcome — clinical, technical, and documentation.

## Ways to Contribute

### Clinical Accuracy
The most valuable contribution is clinical expertise.
- Open a GitHub Issue with the query, the response received, and what the correct response should be
- Reference the specific JTS CPG or clinical source

### Protocol Expansion
- Help identify additional clinical guideline sets to ingest
- Assist with processing non-JTS formatted documents for ChromaDB indexing
- Regional and national protocol sets for international deployment contexts

### Hardware Testing
- Test cdss_client.py on new edge hardware platforms
- Document performance, latency, and power consumption
- Jetson Orin Nano local LLM integration is a priority

### Code
- See open Issues for current development priorities
- Fork the repo, create a feature branch, submit a pull request
- All PRs require a description of what was changed and why

## Development Setup

```bash
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
```

## Running Tests

```bash
export CDSS_SERVER_URL=https://your-server
export CDSS_ACCESS_TOKEN=your-token
python test_cdss.py
```

## Security

- Never commit API keys, server IPs, or tokens
- .env is gitignored — keep all secrets there
- If you discover a security vulnerability open a private Issue

## Code of Conduct

This project is built for environments where errors cost lives. Clinical accuracy is the highest priority. All contributions are reviewed with that standard in mind.

*Guideline-based support only. Not a substitute for clinical judgment.*