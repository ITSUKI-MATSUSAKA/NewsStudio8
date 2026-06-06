import os
from google import genai

API_KEY = "AIzaSyAOxMwPLqAt5FYYAK3YLFcl9tCEUvWz6Ws"
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
