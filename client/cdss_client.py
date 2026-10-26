"""
EdgeCDSS Thin Client - Radxa Zero 3W
Routes queries to arcaneone backend and prints the response
Version: 1.7.0
- lbs to kg auto-conversion for patient safety
- No voice output: the ElevenLabs path is deleted (owner, 2026-10-26). Voice
  is the server's local /speak (Kokoro, on the device).
"""

import os
import re
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.getenv('CDSS_SERVER_URL', 'http://localhost:8000')
DEVICE_ID = os.getenv('DEVICE_ID', 'radxa-zero3')


def preprocess_query(query: str) -> str:
    """Convert lbs to kg for patient safety"""
    def convert_weight(match):
        lbs_val = float(match.group(1))
        kg_val = round(lbs_val / 2.2, 1)
        return f"{lbs_val} lbs ({kg_val} kg)"

    processed = re.sub(
        r'(\d+\.?\d*)\s*(?:lbs?|pounds?)',
        convert_weight,
        query,
        flags=re.IGNORECASE
    )
    return processed


def query_cdss(query: str, voice_mode: str = "brief") -> str:
    """Send query to arcaneone backend and return response"""
    try:
        processed_query = preprocess_query(query)

        if processed_query != query:
            print(f"\n⚠️  Weight converted: {processed_query}")

        payload = {
            "query": processed_query,
            "device_id": DEVICE_ID,
            "timestamp": datetime.datetime.now().isoformat(),
            "voice_mode": voice_mode
        }
        response = requests.post(
            f"{SERVER_URL}/query",
            json=payload,
            timeout=30
        )
        data = response.json()
        return data.get('response', 'No response received')
    except requests.exceptions.ConnectionError:
        return "OFFLINE MODE: No connection to backend. Check network."
    except Exception as e:
        return f"Error: {str(e)}"


def main():
    print("=" * 50)
    print("AUSTERE-CDS | EdgeCDSS-Nano")
    print("Connected to:", SERVER_URL)
    print("Type 'quit' to exit")
    print("=" * 50)

    while True:
        try:
            query = input("\nMEDIC> ").strip()
            if not query:
                continue
            if query.lower() in ['quit', 'exit', 'q']:
                break

            print("\nQuerying JTS protocols...")
            response = query_cdss(query)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\nShutting down.")
            break


if __name__ == "__main__":
    main()
