import urllib.request
import json
import urllib.error

API_KEY = "AIzaSyAOxMwPLqAt5FYYAK3YLFcl9tCEUvWz6Ws"
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
headers = {'Content-Type': 'application/json'}
data = {
    "contents": [{"parts": [{"text": "Hello, write a short sentence."}]}]
}
req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers)
try:
    with urllib.request.urlopen(req) as response:
        print("Success:")
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")
