import urllib.request
import json
import urllib.error

API_KEY = "AIzaSyAOxMwPLqAt5FYYAK3YLFcl9tCEUvWz6Ws"
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
try:
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode('utf-8'))
        for model in data.get('models', []):
            if "flash" in model['name'] or "pro" in model['name']:
                print(f"{model['name']} - {model.get('supportedGenerationMethods', [])}")
except Exception as e:
    print(f"Error: {e}")
