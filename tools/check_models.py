import os
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core import exceptions as google_exceptions

# Load API Key
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Error: GEMINI_API_KEY not found in .env")
    exit(1)

genai.configure(api_key=api_key)

print("Checking available models for your API key...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- Name: {m.name}")
            print(f"  Description: {m.description}")
except (
    OSError,
    RuntimeError,
    ValueError,
    google_exceptions.GoogleAPIError,
    google_exceptions.RetryError,
) as e:
    print(f"Error listing models: {e}")
