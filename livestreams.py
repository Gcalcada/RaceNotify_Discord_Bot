import requests
import time

API_KEY = "AIzaSyDIrgzURwNU8szgrsXRtEGpvYZQMuKcOoc"
INPUT_FILE = "channels_input.txt"
OUTPUT_FILE = "live_matches.txt"

def load_channel_ids():
    with open(INPUT_FILE, "r") as f:
        return [line.strip() for line in f if line.strip().startswith("UC")]

def check_channel_live(channel_id):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "eventType": "live",
        "type": "video",
        "key": API_KEY,
        "maxResults": 1
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if "items" in data and len(data["items"]) > 0:
            video = data["items"][0]
            video_id = video["id"]["videoId"]
            title = video["snippet"]["title"]
            channel_title = video["snippet"]["channelTitle"]
            print(f"✅ LIVE: {channel_title} — {title}")
            return f"https://www.youtube.com/watch?v={video_id}"

        return None
    except Exception as e:
        print(f"❌ Error for channel {channel_id}: {e}")
        return None

def main():
    channel_ids = load_channel_ids()
    live_links = []

    print(f"🔍 Checking {len(channel_ids)} channels for livestreams...\n")

    for i, channel_id in enumerate(channel_ids, 1):
        print(f"[{i}/{len(channel_ids)}] Checking: {channel_id}")
        result = check_channel_live(channel_id)
        if result:
            live_links.append(result)
        time.sleep(0.25)  # avoid quota spikes

    with open(OUTPUT_FILE, "w") as f:
        for url in live_links:
            f.write(url + "\n")

    print(f"\n🎯 Done. {len(live_links)} livestream(s) found and saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
