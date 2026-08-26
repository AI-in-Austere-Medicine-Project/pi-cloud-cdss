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
pip install -r client/requirements.txt
cp .env.example .env
```

## Running Tests

**The offline suite is expected to be green. A red suite blocks merge** — including
a failure you did not cause. A suite that is permanently red cannot tell anyone when
something real breaks, because a new failure is indistinguishable from the standing
noise. If a test is red for a reason you cannot fix, mark it `xfail` with a reason
string naming what it is waiting on, so the count stays honest and the wait is visible.

```bash
cd server && ./run_unit_tests.sh   # offline: no network, no API key, no ChromaDB
```

A test must not assert a moment in the project's history — how many dose contracts
are signed, how many vent cards are live, what is in this deployment's kit. Those are
moving facts, and a test pinned to one goes red the day the system is used as designed.
Assert the invariant instead: prove a fence with a synthetic pending entry, the way
`test_vent_module.py` and `test_drug_contracts.py` do.

The live clinical suite needs a running server and a token:

```bash
export CDSS_SERVER_URL=https://your-server
export CDSS_ACCESS_TOKEN=your-token
bash server/run_tests.sh
```

## Security

- Never commit API keys, server IPs, or tokens
- .env is gitignored — keep all secrets there
- If you discover a security vulnerability open a private Issue

## Code of Conduct

This project is built for environments where errors cost lives. Clinical accuracy is the highest priority. All contributions are reviewed with that standard in mind.

*Guideline-based support only. Not a substitute for clinical judgment.*