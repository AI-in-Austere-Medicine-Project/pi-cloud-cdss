"""
EdgeCDSS Thin Client - Radxa Zero 3W
Routes queries to arcaneone backend, plays response via ElevenLabs
Version: 1.4.0
- TTS medical term expansion with number-attached unit handling
- Voice speed control
- lbs to kg auto-conversion for patient safety
"""

import os
import re
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.getenv('CDSS_SERVER_URL', 'http://34.63.127.8:8000')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
DEVICE_ID = os.getenv('DEVICE_ID', 'radxa-zero3')

TTS_EXPANSIONS = {
    # Common abbreviations
    "e.g.": "for example",
    "i.e.": "that is",
    "etc.": "and so on",
    "vs.": "versus",
    "approx.": "approximately",
    "max.": "maximum",
    "min.": "minimum",
    "sx": "symptoms",
    "dx": "diagnosis",
    "tx": "treatment",
    "hx": "history",
    "px": "patient",
    "w/": "with",
    "w/o": "without",
    "s/p": "status post",
    "c/o": "complains of",
    "h/o": "history of",

    # Routes
    "IV": "intravenous",
    "IO": "intraosseous",
    "IM": "intramuscular",
    "SQ": "subcutaneous",
    "PO": "by mouth",
    "SL": "sublingual",
    "IN": "intranasal",

    # Resuscitation
    "TXA": "tranexamic acid",
    "DCR": "damage control resuscitation",
    "DCS": "damage control surgery",
    "LTOWB": "low titer O whole blood",
    "WB": "whole blood",
    "FFP": "fresh frozen plasma",
    "RBC": "red blood cells",
    "CRYO": "cryoprecipitate",
    "MT": "massive transfusion",
    "REBOA": "resuscitative endovascular balloon occlusion of the aorta",
    "TEG": "thromboelastography",
    "ROTEM": "rotational thromboelastometry",
    "INR": "international normalized ratio",
    "BD": "base deficit",
    "HCT": "hematocrit",
    "SBP": "systolic blood pressure",
    "MAP": "mean arterial pressure",
    "HR": "heart rate",
    "POI": "point of injury",

    # Respiratory
    "ARDS": "acute respiratory distress syndrome",
    "LPV": "lung protective ventilation",
    "VT": "tidal volume",
    "PBW": "predicted body weight",
    "PPLAT": "plateau pressure",
    "PIP": "peak inspiratory pressure",
    "PEEP": "positive end expiratory pressure",
    "FiO2": "fraction of inspired oxygen",
    "SpO2": "oxygen saturation",
    "SaO2": "arterial oxygen saturation",
    "PaO2": "partial pressure of arterial oxygen",
    "PaCO2": "partial pressure of arterial carbon dioxide",
    "ABG": "arterial blood gas",
    "CPAP": "continuous positive airway pressure",
    "APRV": "airway pressure release ventilation",
    "iNO": "inhaled nitric oxide",
    "ECMO": "extracorporeal membrane oxygenation",
    "vvECLS": "veno-venous extracorporeal life support",
    "CCATT": "critical care air transport team",
    "ACCET": "advanced critical care evacuation team",
    "ETT": "endotracheal tube",
    "RSI": "rapid sequence intubation",

    # TBI/Neuro
    "TBI": "traumatic brain injury",
    "GCS": "Glasgow Coma Score",
    "ICP": "intracranial pressure",
    "CPP": "cerebral perfusion pressure",
    "PbtO2": "brain tissue oxygen",
    "NPi": "neurological pupillary index",
    "EtCO2": "end tidal carbon dioxide",
    "EVD": "external ventricular drain",
    "SDH": "subdural hematoma",
    "EDH": "epidural hematoma",
    "mTBI": "mild traumatic brain injury",
    "MACE2": "military acute concussion evaluation two",
    "DVT": "deep vein thrombosis",
    "SCD": "sequential compression device",
    "NaCl": "sodium chloride",

    # System
    "MTF": "medical treatment facility",
    "MEDEVAC": "medical evacuation",
    "TCCC": "tactical combat casualty care",
    "ATLS": "advanced trauma life support",
    "MEDROE": "medical rules of eligibility",
    "JTS": "joint trauma system",
    "CPG": "clinical practice guideline",
    "ORS": "oral rehydration solution",

    # Vitals/Labs
    "BID": "twice daily",
    "TID": "three times daily",
    "QID": "four times daily",
    "PRN": "as needed",
    "Hgb": "hemoglobin",
    "WBC": "white blood cells",
    "plt": "platelets",
    "Na": "sodium",
    "K": "potassium",
    "Ca": "calcium",
    "Mg": "magnesium",
    "pH": "potential of hydrogen",
    "pCO2": "partial pressure of carbon dioxide",
    "HCO3": "bicarbonate",
    "Lac": "lactate",
    "PT": "prothrombin time",
    "PTT": "partial thromboplastin time",
}


def preprocess_query(query: str) -> str:
    """
    Pre-process query before sending to backend.
    Converts lbs/pounds to kg for patient safety.
    """
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


def expand_for_tts(text: str) -> str:
    """Expand medical acronyms and units for natural TTS pronunciation"""
    tts_text = text

    # Remove markdown formatting
    tts_text = re.sub(r'\*\*(.*?)\*\*', r'\1', tts_text)
    tts_text = re.sub(r'[#*_`]', '', tts_text)

    # Handle number-attached compound units first (most specific to least)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mcg/kg/min', r'\1 micrograms per kilogram per minute', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mg/kg/min', r'\1 milligrams per kilogram per minute', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mcg/kg', r'\1 micrograms per kilogram', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mg/kg', r'\1 milligrams per kilogram', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mcg/mL', r'\1 micrograms per milliliter', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mg/mL', r'\1 milligrams per milliliter', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mL/hr', r'\1 milliliters per hour', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mL/min', r'\1 milliliters per minute', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*L/min', r'\1 liters per minute', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mmHg', r'\1 millimeters of mercury', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*cmH2O', r'\1 centimeters of water', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mEq', r'\1 milliequivalents', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mmol', r'\1 millimoles', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mcg', r'\1 micrograms', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mL', r'\1 milliliters', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*mg', r'\1 milligrams', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*kg', r'\1 kilograms', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*g\b', r'\1 grams', tts_text)
    tts_text = re.sub(r'(\d+\.?\d*)\s*L\b', r'\1 liters', tts_text)

    # Then expand standalone acronyms
    for acronym, expansion in TTS_EXPANSIONS.items():
        tts_text = re.sub(r'\b' + re.escape(acronym) + r'\b', expansion, tts_text)

    return tts_text


def query_cdss(query: str, voice_mode: str = "brief") -> str:
    """Send query to arcaneone and return response"""
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


def speak(text: str):
    """Play response via ElevenLabs TTS with medical term expansion"""
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings
        import pygame
        import io

        tts_text = expand_for_tts(text)

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.text_to_speech.convert(
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            text=tts_text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                speed=0.85
            )
        )

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