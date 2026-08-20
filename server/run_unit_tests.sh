#!/bin/bash
# EdgeCDSS — offline unit/regression suite.
#
# No network, no OpenAI key, no server, no ChromaDB. Covers the deterministic
# layer, the safety gate, the clinical router's alias table and the session
# logger. The live 24-case endpoint suite is run_tests.sh — a separate, manual,
# network-dependent check that is NOT part of this gate.
set -u
cd "$(dirname "$0")"
exec python3 -m pytest -q . "$@"
