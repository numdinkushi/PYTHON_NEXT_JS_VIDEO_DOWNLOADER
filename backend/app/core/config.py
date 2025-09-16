import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent

# Downloads directory
DOWNLOADS_DIR = os.path.expanduser("~/Downloads/youtube_videos")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# CORS settings
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001", 
    "http://localhost:4900"
]

# Server settings
HOST = "0.0.0.0"
PORT = 8000

# yt-dlp settings
YT_DLP_OPTIONS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'extractor_retries': 3,
    'fragment_retries': 3,
    'retries': 3,
    'sleep_interval': 1,
    'max_sleep_interval': 5,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    },
    'extractor_args': {
        'youtube': {
            'skip': ['dash', 'hls'],
            'player_skip': ['configs'],
            'player_client': ['android', 'web', 'ios', 'tv_embedded'],
            'comment_sort': ['top'],
            'max_comments': [0],
        }
    }
}
