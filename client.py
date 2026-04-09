#!/usr/bin/env python3
"""
Pi Cloud CDSS Client
Raspberry Pi 4 client for cloud-based clinical decision support
"""

import requests
import json
from pathlib import Path
from typing import Dict, Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class CloudCDSSClient:
    """
    Lightweight client for Pi 4 that connects to cloud-based CDSS
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the cloud client"""
        self.config = self.load_config(config_path)
        self.vm_endpoint = self.config.get('vm_endpoint', 'http://localhost:5000')
        self.openai_key = os.getenv('OPENAI_API_KEY')
        
        print("✓ Pi Cloud CDSS Client initialized")
        print(f"  VM Endpoint: {self.vm_endpoint}")
    
    def load_config(self, config_path: str) -> Dict:
        """Load configuration from file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠ Config file not found. Creating default config...")
            default_config = {
                "vm_endpoint": "http://localhost:5000",
                "voice_enabled": True
            }
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
    
    def query(self, clinical_question: str) -> Optional[Dict]:
        """
        Send clinical query to VM backend
        
        Args:
            clinical_question: Clinical scenario or question
            
        Returns:
            Response with guidance and sources
        """
        print(f"\n{'='*60}")
        print(f"Query: {clinical_question}")
        print(f"{'='*60}\n")
        
        try:
            # Send to VM endpoint
            response = requests.post(
                f"{self.vm_endpoint}/query",
                json={"question": clinical_question},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                print(f"✗ Error: Server returned {response.status_code}")
                return None
                
        except requests.exceptions.ConnectionError:
            print(f"✗ Cannot connect to VM at {self.vm_endpoint}")
            print("  Make sure the VM server is running")
            return None
        except Exception as e:
            print(f"✗ Error: {e}")
            return None
    
    def display_response(self, result: Dict):
        """Display the clinical guidance response"""
        if not result:
            return
        
        print(f"{'='*60}")
        print("CLINICAL GUIDANCE")
        print(f"{'='*60}\n")
        print(result.get('response', 'No response'))
        print(f"\n{'='*60}")
        print("Sources:")
        for source in result.get('sources', []):
            print(f"  - {source}")
        print(f"{'='*60}")
        print("⚠️  FOR EDUCATIONAL PURPOSES ONLY")
        print(f"{'='*60}\n")
    
    def interactive_mode(self):
        """Run interactive query session"""
        print("\n" + "="*60)
        print("PI CLOUD CDSS CLIENT")
        print("Cloud-Based Clinical Decision Support")
        print("="*60)
        print("\nCommands:")
        print("  Type your clinical question")
        print("  'quit' - Exit")
        print("  'test' - Test VM connection")
        print("="*60 + "\n")
        
        while True:
            try:
                user_input = input("Clinical Question: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\nExiting...")
                    break
                
                if user_input.lower() == 'test':
                    print("Testing VM connection...")
                    try:
                        response = requests.get(f"{self.vm_endpoint}/health", timeout=5)
                        if response.status_code == 200:
                            print("✓ VM is reachable")
                        else:
                            print(f"✗ VM returned status {response.status_code}")
                    except:
                        print(f"✗ Cannot reach VM at {self.vm_endpoint}")
                    continue
                
                # Send query to VM
                result = self.query(user_input)
                self.display_response(result)
                
            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    client = CloudCDSSClient()
    client.interactive_mode()