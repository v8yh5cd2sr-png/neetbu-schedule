import json, os, re, urllib.request, urllib.parse
from datetime import datetime, timedelta

API_KEY = os.environ["YOUTUBE_API_KEY"]
CHANNEL_ID = "UClNdVSK1uy2xFHTaXZYXopw"
PLAYLIST_ID = "UU" + CHANNEL_ID[2:]
MAX_PAGES = 100
SHORT_SECONDS = 60  # この秒数以下ならショート扱い

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

def game_name(title):
    for m in re.finditer(r"【(.+?)】", title):
        name = m.group(1).strip()
        if re.fullmatch(r"(?:#|No\.?|Part|Ep\.?|第)?\s*[0-9０-９]+\s*(?:話|回|日目|章|夜|本目)?", name, re.I):
            continue
        if re.fullmatch(r"(?:前|中|後|完結|最終)(?:編|回|話)?|最終回|終", name):
            continue
        return name
    return ""

def to_jst(s):
    # YouTubeの時刻(UTC)を日本時間に直す。小数秒があっても動くようにする
    t = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9)
    return t

# 今ある記録を読み込む
try:
    with open("videos.json", encoding="utf-8") as f:
        videos = json.load(f)
except FileNotFoundError:
    videos = []
known = {vid_id(v["url"]) for v in videos}

# 1) 新しい動画を追加（全ページ）
added = 0
page_token = None
for page in range(MAX_PAGES):
    params = {"part": "snippet", "playlistId": PLAYLIST_ID, "maxResults": 50}
    if page_token:
        params["pageToken"] = page_token
    data = api("playlistItems", params)
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

# 2) 種類と配信時間を判定（50本ずつ詳細を取得）
by_id = {vid_id(v["url"]): v for v in videos if vid_id(v["url"])}
ids = list(by_id)
for i in range(0, len(ids), 50):
    chunk = ids[i:i + 50]
    data = api("videos", {
        "part": "contentDetails,liveStreamingDetails",
        "id": ",".join(chunk),
    })
    for item in data["items"]:
        v = by_id[item["id"]]
        live = item.get("liveStreamingDetails")
        if live:
            v["type"] = "配信"
            if live.get("actualStartTime"):
                st = to_jst(live["actualStartTime"])
                v["start"] = st.strftime("%Y-%m-%dT%H:%M")
                v["date"] = st.strftime("%Y-%m-%d")  # 配信は開始日を日付にする
                if live.get("actualEndTime"):
                    en = to_jst(live["actualEndTime"])
                    v["end"] = en.strftime("%Y-%m-%dT%H:%M")
                    v["hours"] = round((en - st).total_seconds() / 3600, 1)
        elif seconds(item["contentDetails"]["duration"]) <= SHORT_SECONDS or "#shorts" in v["title"].lower():
            v["type"] = "ショート"
        else:
            v["type"] = "動画"
# 3) ゲーム名を保存（表記ゆれ統一・除外つき。game_fixed の動画は触らない）
try:
    with open("game_aliases.json", encoding="utf-8") as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {}
alias = {}
for main, names in cfg.get("aliases", {}).items():
    for n in names:
        alias[n.lower()] = main
ignore = {n.lower() for n in cfg.get("ignore", [])}

for v in videos:
    if v.get("game_fixed"):
        continue
    g = game_name(v["title"])
    if g.lower() in ignore:
        g = ""
    v["game"] = alias.get(g.lower(), g)

