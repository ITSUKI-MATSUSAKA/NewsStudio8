import urllib.request
import json
import zipfile
import io

# Get latest runs
url = "https://api.github.com/repos/ITSUKI-MATSUSAKA/NewsStudio8/actions/runs?per_page=1"
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        run_id = data['workflow_runs'][0]['id']
        print(f"Latest run ID: {run_id}")
        
    log_url = f"https://api.github.com/repos/ITSUKI-MATSUSAKA/NewsStudio8/actions/runs/{run_id}/logs"
    print(f"Fetching logs from: {log_url}")
    req_logs = urllib.request.Request(log_url)
    with urllib.request.urlopen(req_logs) as resp_logs:
        log_data = resp_logs.read()
        
    with zipfile.ZipFile(io.BytesIO(log_data)) as z:
        for name in z.namelist():
            if "Run update_news.py.txt" in name:
                print(f"\n--- {name} ---")
                content = z.read(name).decode('utf-8')
                lines = content.split('\n')
                for line in lines[-50:]:
                    print(line)
except Exception as e:
    print(e)
