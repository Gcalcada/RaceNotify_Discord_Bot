import requests
from urllib.parse import urlparse

# 🔐 Your YouTube API Key (replace if regenerated)
API_KEY = "AIzaSyDIrgzURwNU8szgrsXRtEGpvYZQMuKcOoc"

INPUT_FILE = "channels_input.txt"
OUTPUT_FILE = "channel_ids_output.txt"

def extract_handle_or_path(url):
    path = urlparse(url).path.strip("/")
    if path.startswith("@"):
        return "handle", path[1:]
    else:
        return "customUrl", path.split("/")[-1]

def resolve_channel_id(identifier_type, value):
    if identifier_type == "handle":
        url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forHandle={value}&key={API_KEY}"
    else:
        url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forUsername={value}&key={API_KEY}"

    response = requests.get(url)
    if response.status_code != 200:
        print(f"[!] API error for {value}: {response.status_code}")
        return None
    data = response.json()
    if "items" in data and len(data["items"]) > 0:
        return data["items"][0]["id"]
    else:
        print(f"[!] No channel found for {value}")
        return None

def main():
    with open(INPUT_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    channel_ids = []

    for url in urls:
        id_type, value = extract_handle_or_path(url)
        print(f"[+] Resolving {value} ({id_type})...")
        channel_id = resolve_channel_id(id_type, value)
        if channel_id:
            print(f"    → ID: {channel_id}")
            channel_ids.append(channel_id)
        else:
            print(f"    → Failed.")

    with open(OUTPUT_FILE, "w") as f:
        for cid in channel_ids:
            f.write(cid + "\n")

    print(f"\n✅ Done! Saved {len(channel_ids)} channel IDs to '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    main()
