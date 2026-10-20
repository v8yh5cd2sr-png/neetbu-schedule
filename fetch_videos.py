import json, os, re, urllib.request, urllib.parse
from datetime import datetime, timedelta

API_KEY = os.environ["YOUTUBE_API_KEY"]
CHANNEL_ID = "UCFQu6Q-9LAS3KoEuRDNkzGA"
PLAYLIST_ID = "UU" + CHANNEL_ID[2:]
MAX_PAGES = 100
SHORT_SECONDS = 60

def vid_id(url):
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return m.group(1) if m else None

def api(endpoint, params):
    params["key"] = API_KEY
    url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as res:
        return json.load(res)

def seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    d, h, mi, s = [int(x or 0) for x in m.groups()] if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s

def clean(name):
    return name.strip(" 　-－―ー~〜|｜/／")

def game_name(title, vtype=""):
    # 配信：一番後ろの【】がゲーム名（最初の【】は誰の視点か）
    if vtype == "配信":
        found = re.findall(r"【(.+?)】", title)
        if len(found) >= 2:
            return clean(found[-1])
        return "雑談"
    # 動画：一番後ろのハイフン以降がゲーム名
    parts = re.split(r"\s*[-－―]\s*", title)
    if len(parts) >= 2:
        name = clean(parts[-1])
        name = re.sub(r"^【(.+)】$", r"\1", name)  # 【】で囲まれていたら外す
        if name:
            return name
    return "雑談"


def to_jst(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9)

print("チャンネルID:", CHANNEL_ID, "/ 再生リスト:", PLAYLIST_ID)

try:
    with open("videos.json", encoding="utf-8") as f:
        videos = json.load(f)
except FileNotFoundError:
    videos = []
known = {vid_id(v["url"]) for v in videos}

added = 0
page_token = None
for page in range(MAX_PAGES):
    params = {"part": "snippet", "playlistId": PLAYLIST_ID, "maxResults": 50}
    if page_token:
        params["pageToken"] = page_token
    data = api("playlistItems", params)
    print(f"ページ{page + 1}: {len(data.get('items', []))}件取得")
    for item in data["items"]:
        s = item["snippet"]
        vid = s["resourceId"]["videoId"]
        if vid in known or s["title"] in ("Private video", "Deleted video"):
            continue
        jst = to_jst(s["publishedAt"])
        videos.append({
            "title": s["title"],
            "date": jst.strftime("%Y-%m-%d"),
            "url": "https://www.youtube.com/watch?v=" + vid,
            "type": "動画",
        })
        known.add(vid)
        added += 1
    page_token = data.get("nextPageToken")
    if not page_token:
        break

by_id = {vid_id(v["url"]): v for v in videos if vid_id(v["url"])}
ids = list(by_id)
for i in range(0, len(ids), 50):
    chunk = ids[i:i + 50]
    data = api("videos", {"part": "contentDetails,liveStreamingDetails", "id": ",".join(chunk)})
    for item in data["items"]:
        v = by_id[item["id"]]
        live = item.get("liveStreamingDetails")
        if live:
            v["type"] = "配信"
            if live.get("actualStartTime"):
                st = to_jst(live["actualStartTime"])
                v["start"] = st.strftime("%Y-%m-%dT%H:%M")
                v["date"] = st.strftime("%Y-%m-%d")
                if live.get("actualEndTime"):
                    en = to_jst(live["actualEndTime"])
                    v["end"] = en.strftime("%Y-%m-%dT%H:%M")
                    v["hours"] = round((en - st).total_seconds() / 3600, 1)
        elif seconds(item["contentDetails"]["duration"]) <= SHORT_SECONDS or "#shorts" in v["title"].lower():
            v["type"] = "ショート"
        else:
            v["type"] = "動画"

for v in videos:
    if not v.get("game_fixed"):
        v["game"] = game_name(v["title"])

videos.sort(key=lambda v: v.get("start") or v["date"], reverse=True)
with open("videos.json", "w", encoding="utf-8") as f:
    json.dump(videos, f, ensure_ascii=False, indent=2)
lives = sum(1 for v in videos if v.get("start"))
print(f"{added}本追加、全{len(videos)}本、うち配信時間つき{lives}本")
