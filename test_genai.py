import os
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=API_KEY)
try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='こんにちは。テストです。'
    )
    print("Success:")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
