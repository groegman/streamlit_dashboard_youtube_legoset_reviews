import sqlite3
import yt_dlp
from yt_dlp.utils import DownloadError
from datetime import datetime
import csv
import json
import requests
import time

start_time = time.time()

# 📌 Connect to SQLite database
conn = sqlite3.connect("youtube_videos.db")
cursor = conn.cursor()

# 📥 Load LEGO sets from CSV (only add new ones)
def load_legosets_from_csv(csv_file_path):
    with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        new_count = 0
        for row in reader:
            number = row["Number"].strip()
            cursor.execute("SELECT 1 FROM legosets WHERE Number = ?", (number,))
            if cursor.fetchone():
                print(f"⚠️ Set {number} already exists, skipping...")
                continue
            values = tuple(row[col].strip() for col in reader.fieldnames)
            placeholders = ",".join(["?"] * len(values))
            cursor.execute(f"INSERT INTO legosets VALUES ({placeholders})", values)
            new_count += 1
        conn.commit()
        print(f"✅ {new_count} new LEGO sets added to database.")

# 🔎 Search videos and store with lego_number
def search_videos(query, lego_number, max_results=50):
    ydl_opts = {
        "quiet": True,
        "sleep_interval": 3,
        "max_sleep_interval": 4,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)["entries"]
        except DownloadError as e:
            if "Premieres in" in str(e):
                print(f"⏩ Skipping premiere search result for: {query}")
                return
            else:
                raise

        for video in results:
            if not video or video.get("is_unavailable") or video.get("age_limit", 0) > 0:
                print(f"🔒 Skipping inaccessible or age-restricted video: {video.get('id', 'unknown')}")
                continue

            video_id = video["id"]
            title = video.get("title", "")
            duration = video.get("duration", 0)
            views = video.get("view_count", 0)
            caps = video.get("automatic_captions", {})

            # 🎯 Filterbedingungen
            if (
                views < 500 or
                duration is None or duration < 60 or
                "review" not in title.lower() or
                not any(lang in caps for lang in ["en", "de", "da", "fr", "it"])
            ):
                print(f"⛔️ Skipping {video_id} ({title}) - Filtered out")
                continue

            cursor.execute("SELECT COUNT(*) FROM videos WHERE video_id = ?", (video_id,))
            if cursor.fetchone()[0] > 0:
                print(f"⚠️ Video {video_id} already exists, skipping...")
                continue

            uploader = video["uploader"]
            upload_date = video["upload_date"]
            transcript_available = "Ja" if caps else "Nein"
            languages = ", ".join(caps.keys())

            cursor.execute("""
                INSERT INTO videos (video_id, title, uploader, upload_date, views, duration, transcript, languages, lego_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (video_id, title, uploader, upload_date, views, duration, transcript_available, languages, lego_number))

    conn.commit()

# 📋 Extract and store transcript
def get_transcripts(video_id):
    cursor.execute("SELECT COUNT(*) FROM video_details WHERE video_id = ?", (video_id,))
    if cursor.fetchone()[0] > 0:
        print(f"⚠️ Video {video_id} already exists in details, skipping...")
        return

    ydl_opts = {
        "quiet": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "skip_download": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            video_info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

            if video_info.get("age_limit", 0) > 0 or video_info.get("is_unavailable"):
                print(f"🔒 Skipping restricted or unavailable video {video_id}")
                return

            description = video_info.get("description", "No description available")
            captions = video_info.get("automatic_captions", {})

            if "en" not in captions:
                print(f"⛔️ No English transcript for {video_id}, skipping...")
                return

            # ✅ Load English transcript
            url = captions["en"][0]["url"] + "&fmt=json3"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                segments = []
                for event in data.get("events", []):
                    for seg in event.get("segs", []):
                        segments.append(seg.get("utf8", "").replace("\n", " "))
                transcript_text = " ".join(segments).strip()
            else:
                print(f"❌ Error downloading transcript for {video_id}")
                transcript_text = "❌ Error downloading transcript"

        except DownloadError as de:
            error_msg = str(de)
            if "Sign in to confirm your age" in error_msg:
                print(f"🔞 Skipping age-restricted video {video_id}")
                return
            else:
                print(f"❌ DownloadError for {video_id}: {error_msg}")
                transcript_text = f"DownloadError: {error_msg}"
                description = "Download error"

        except Exception as e:
            print(f"❌ General error for {video_id}: {e}")
            description = "Error loading video"
            transcript_text = f"Error: {e}"

        # 📥 Save to DB only if transcript was attempted
        cursor.execute("""
            INSERT INTO video_details (video_id, description, transcript)
            VALUES (?, ?, ?)
        """, (video_id, description, transcript_text))
        conn.commit()

        print(f"✅ Stored transcript for video {video_id}")

# 📁 Load new LEGO sets
load_legosets_from_csv("starwars_2025.csv")

# 🔍 Suche nur für Sets ohne Videos
cursor.execute("""
    SELECT Number, SetName FROM legosets
    WHERE LOWER(PackagingType) = 'box'
    AND Number NOT IN (SELECT DISTINCT lego_number FROM videos)
""")
sets_to_search = cursor.fetchall()

print(f"🔍 Searching for videos for {len(sets_to_search)} new LEGO sets...")
for number, name in sets_to_search:
    query = f"LEGO {number} review"
    print(f"🔍 Searching: {query}")
    search_videos(query, lego_number=number)

# 📥 Retrieve and store transcripts
cursor.execute("SELECT video_id FROM videos")
video_ids = [row[0] for row in cursor.fetchall()]
for video_id in video_ids:
    get_transcripts(video_id)

conn.close()
elapsed_time = time.time() - start_time
minutes = int(elapsed_time // 60)
seconds = int(elapsed_time % 60)
print(f"✅ All done! ⏱️ Script runtime: {minutes} min {seconds} sec")
