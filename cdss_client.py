"""
EdgeCDSS Thin Client - Radxa Zero 3W
Routes queries to arcaneone backend, plays response via ElevenLabs
"""

import os
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.getenv('CDSS_SERVER_URL', 'http://35.222.168.239:8000')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
DEVICE_ID = os.getenv('DEVICE_ID', 'radxa-zero3')

def query_cdss(query: str, voice_mode: str = "brief") -> str:
    """Send query to arcaneone and return response"""
    try:
        payload = {
            "query": query,
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

def speak(text: str):
    """Play response via ElevenLabs TTS"""
    try:
        from elevenlabs.client import ElevenLabs
        import pygame
        import io
        
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.text_to_speech.convert(
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            text=text,
            model_id="eleven_multilingual_v2"
        )
        
        # Play audio
        audio_bytes = b"".join(audio)
        pygame.mixer.init()
        pygame.mixer.music.load(io.BytesIO(audio_bytes))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
    except Exception as e:
        print(f"TTS unavailable: {e}")
        print(f"\nRESPONSE:\n{text}")

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
            speak(response)

        except KeyboardInterrupt:
            print("\nShutting down.")
            break

if __name__ == "__main__":
    main()