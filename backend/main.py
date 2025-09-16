from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import yt_dlp
import os
import tempfile
import json
from typing import List, Optional, Dict
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import shutil
import hashlib
import time
from datetime import datetime
import uuid
import re

# Update yt-dlp to latest version first
import subprocess
import sys


def update_yt_dlp():
    """Update yt-dlp to latest version"""
    try:
        subprocess.run([sys.executable, "-m", "pip", "install",
                       "--upgrade", "yt-dlp"], check=True)
        print("✅ yt-dlp updated to latest version")
    except Exception as e:
        print(f"⚠️ Could not update yt-dlp: {e}")


# Call this at startup
# update_yt_dlp()

app = FastAPI(title="YouTube Downloader API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                   "http://localhost:3001", "http://localhost:4900"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VideoInfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str


class ResumeRequest(BaseModel):
    download_id: str


class VideoFormat(BaseModel):
    format_id: str
    ext: str
    resolution: str
    filesize: Optional[int]
    vcodec: str
    acodec: str


class VideoInfo(BaseModel):
    title: str
    duration: str
    thumbnail: str
    formats: List[VideoFormat]


# Create organized downloads directory
DOWNLOADS_DIR = os.path.expanduser("~/Downloads/youtube_videos")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
print(f"📁 Downloads directory created: {DOWNLOADS_DIR}")

# Global progress tracking
download_progress = {}
progress_subscribers = {}  # For real-time updates


def get_download_id(url: str, format_id: str) -> str:
    """Generate unique download ID based on URL and format"""
    content = f"{url}_{format_id}"
    return hashlib.md5(content.encode()).hexdigest()


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to remove problematic characters"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'[\uff1a\uff0c\uff01\uff1f]', '', filename)
    filename = filename.strip()
    return filename


def get_video_info(url: str) -> dict:
    """Extract video information using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        # Enhanced anti-detection measures
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        # Enhanced extractor options to fix signature extraction
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls'],
                'player_skip': ['configs'],
                'player_client': ['android', 'web', 'ios', 'tv_embedded'],
                'comment_sort': ['top'],
                'max_comments': [0],
            }
        },
        # Retry options
        'extractor_retries': 3,
        'fragment_retries': 3,
        'retries': 3,
        # Sleep between requests
        'sleep_interval': 1,
        'max_sleep_interval': 5,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to extract video info: {str(e)}")


def format_duration(seconds):
    """Convert seconds to MM:SS or HH:MM:SS format"""
    if not seconds:
        return "Unknown"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if bytes_value == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(bytes_value.bit_length() / 10)
    return f"{bytes_value / (1 << (i * 10)):.1f} {size_names[i]}"


def format_speed(bytes_per_sec):
    """Format speed to human readable format"""
    return format_bytes(bytes_per_sec) + "/s"


def format_eta(seconds):
    """Format ETA to human readable format"""
    if seconds is None or seconds < 0:
        return "Unknown"
    return format_duration(int(seconds))


def get_resolution_string(format_info):
    """Get resolution string from format info"""
    if format_info.get('height'):
        return f"{format_info['height']}p"
    elif format_info.get('width') and format_info.get('height'):
        return f"{format_info['width']}x{format_info['height']}"
    elif 'format_note' in format_info:
        return format_info['format_note']
    else:
        return "Unknown"


def progress_hook(d):
    """Progress hook for yt-dlp downloads"""
    download_id = d.get('info_dict', {}).get('_download_id')
    if not download_id:
        return

    print(f"📊 Progress hook called for {download_id}: {d['status']}")

    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded_bytes = d.get('downloaded_bytes', 0)
        speed = d.get('speed', 0)
        eta = d.get('eta')

        progress = (downloaded_bytes / total_bytes *
                    100) if total_bytes > 0 else 0

        # Update global progress
        progress_data = {
            'status': 'downloading',
            'progress': min(progress, 100),
            'downloaded_bytes': downloaded_bytes,
            'total_bytes': total_bytes,
            'speed': format_speed(speed) if speed else "0 B/s",
            'eta': format_eta(eta),
            'updated_at': datetime.now().isoformat()
        }

        download_progress[download_id] = progress_data

        # Notify subscribers
        if download_id in progress_subscribers:
            for queue in progress_subscribers[download_id]:
                try:
                    queue.put_nowait(progress_data)
                except:
                    pass

        print(f"📊 [{download_id[:8]}] {progress:.1f}% - {format_speed(speed) if speed else '0 B/s'} - ETA: {format_eta(eta)}")

    elif d['status'] == 'finished':
        progress_data = {
            'status': 'completed',
            'progress': 100,
            'updated_at': datetime.now().isoformat()
        }
        download_progress[download_id] = progress_data

        # Notify subscribers
        if download_id in progress_subscribers:
            for queue in progress_subscribers[download_id]:
                try:
                    queue.put_nowait(progress_data)
                except:
                    pass

        print(f"✅ [{download_id[:8]}] Download completed")

    elif d['status'] == 'error':
        progress_data = {
            'status': 'failed',
            'error': str(d.get('error', 'Unknown error')),
            'updated_at': datetime.now().isoformat()
        }
        download_progress[download_id] = progress_data

        # Notify subscribers
        if download_id in progress_subscribers:
            for queue in progress_subscribers[download_id]:
                try:
                    queue.put_nowait(progress_data)
                except:
                    pass

        print(
            f"❌ [{download_id[:8]}] Download failed: {d.get('error', 'Unknown error')}")


@app.post("/video-info", response_model=VideoInfo)
async def get_video_info_endpoint(request: VideoInfoRequest):
    """Get video information and available formats"""
    print(f"🔍 Received video info request for: {request.url}")
    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            info = await loop.run_in_executor(executor, get_video_info, request.url)

        print(
            f"✅ Successfully extracted info for: {info.get('title', 'Unknown')}")

        formats = []
        seen_formats = set()

        for f in info.get('formats', []):
            # Skip audio-only formats
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                continue

            # Skip video-only formats without audio
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none':
                continue

            resolution = get_resolution_string(f)
            format_key = (f.get('height', 0), f.get(
                'ext', ''), f.get('format_id', ''))
            if format_key in seen_formats:
                continue
            seen_formats.add(format_key)

            # Only include formats with both video and audio
            if f.get('vcodec') and f.get('vcodec') != 'none' and f.get('acodec') and f.get('acodec') != 'none':
                formats.append(VideoFormat(
                    format_id=f['format_id'],
                    ext=f.get('ext', 'mp4'),
                    resolution=resolution,
                    filesize=f.get('filesize'),
                    vcodec=f.get('vcodec', 'unknown'),
                    acodec=f.get('acodec', 'unknown')
                ))

        def sort_key(format_item):
            height = 0
            if format_item.resolution.endswith('p'):
                try:
                    height = int(format_item.resolution.replace('p', ''))
                except:
                    height = 0
            format_preference = 0 if format_item.ext == 'mp4' else 1
            return (-height, format_preference)

        formats.sort(key=sort_key)

        print(f"📋 Found {len(formats)} video formats with audio")
        for fmt in formats[:5]:
            print(
                f"   - {fmt.resolution} {fmt.ext.upper()} ({fmt.format_id}) - {fmt.vcodec}/{fmt.acodec}")

        return VideoInfo(
            title=info.get('title', 'Unknown Title'),
            duration=format_duration(info.get('duration')),
            thumbnail=info.get('thumbnail', ''),
            formats=formats
        )

    except Exception as e:
        print(f"❌ Error extracting video info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download")
async def download_video(request: DownloadRequest):
    """Start download and return download ID immediately"""
    download_id = get_download_id(request.url, request.format_id)

    print(f"⬇️ Starting download: {request.url} (format: {request.format_id})")
    print(f"📋 Download ID: {download_id}")

    # Check if already downloading
    if download_id in download_progress:
        existing = download_progress[download_id]
        if existing['status'] in ['downloading']:
            return {
                "download_id": download_id,
                "message": "Download task already exists",
                "status": existing['status'],
                "progress": existing['progress']
            }

    # Initialize progress tracking
    download_progress[download_id] = {
        'status': 'downloading',
        'progress': 0,
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'speed': "0 B/s",
        'eta': "Unknown",
        'updated_at': datetime.now().isoformat()
    }

    # Start download in background
    async def download_task():
        try:
            # Get video info for title
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                info = await loop.run_in_executor(executor, get_video_info, request.url)

            title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(title)

            # Prepare output filename
            ext = request.format_id.split(
                '-')[1] if '-' in request.format_id else 'mp4'
            output_filename = f"{safe_title}.{ext}"
            output_path = os.path.join(DOWNLOADS_DIR, output_filename)

            # Enhanced yt-dlp options with anti-detection measures
            ydl_opts = {
                # Ensure we get both video and audio
                'format': f"{request.format_id}+bestaudio/best",
                'outtmpl': output_path,
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'extractor_retries': 5,
                'fragment_retries': 5,
                'retries': 5,
                'http_chunk_size': 10485760,
                # Reduce concurrent downloads to avoid detection
                'concurrent_fragment_downloads': 1,
                'sleep_interval': 1,  # Add delay between requests
                'max_sleep_interval': 5,
                # Anti-detection measures
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                },
                # Audio/Video merging options
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }, {
                    'key': 'FFmpegMetadata',
                }],
                'merge_output_format': 'mp4',  # Force MP4 output
                'prefer_ffmpeg': True,  # Use FFmpeg for merging
                'ffmpeg_location': None,  # Use system FFmpeg
                # Additional anti-detection
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],  # Skip problematic formats
                        'player_skip': ['configs'],
                    }
                }
            }

            def download_video_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Extract info first
                    info_dict = ydl.extract_info(request.url, download=False)
                    # Add download_id to info_dict
                    info_dict['_download_id'] = download_id
                    print(
                        f"🔍 Info extracted, starting download with ID: {download_id}")

                    # Download with progress tracking
                    ydl.download([request.url])

            # Run download in thread pool
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, download_video_sync)

            # Check if file was downloaded successfully
            if os.path.exists(output_path):
                progress_data = {
                    'status': 'completed',
                    'progress': 100,
                    'filename': output_filename,
                    'file_path': output_path,
                    'updated_at': datetime.now().isoformat()
                }
                download_progress[download_id] = progress_data

                # Notify subscribers
                if download_id in progress_subscribers:
                    for queue in progress_subscribers[download_id]:
                        try:
                            queue.put_nowait(progress_data)
                        except:
                            pass

                print(f"✅ Download completed: {output_filename}")
            else:
                raise Exception("File was not downloaded")

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Download failed: {error_msg}")

            progress_data = {
                'status': 'failed',
                'error': error_msg,
                'updated_at': datetime.now().isoformat()
            }
            download_progress[download_id] = progress_data

            # Notify subscribers
            if download_id in progress_subscribers:
                for queue in progress_subscribers[download_id]:
                    try:
                        queue.put_nowait(progress_data)
                    except:
                        pass

    # Start the download task
    asyncio.create_task(download_task())

    # Return immediately with download ID
    return {
        "download_id": download_id,
        "message": "Download started",
        "status": "downloading"
    }

# Add a fallback download method


@app.post("/download-fallback")
async def download_video_fallback(request: VideoInfoRequest):
    """Download video using fallback method with 720p quality"""
    download_id = get_download_id(request.url, "fallback")

    print(f"⬇️ Starting fallback download: {request.url}")
    print(f"📋 Download ID: {download_id}")

    # Check if already downloading
    if download_id in download_progress:
        existing = download_progress[download_id]
        if existing['status'] in ['downloading']:
            return {
                "download_id": download_id,
                "message": "Download task already exists",
                "status": existing['status'],
                "progress": existing['progress']
            }

    # Initialize progress tracking
    download_progress[download_id] = {
        'status': 'downloading',
        'progress': 0,
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'speed': "0 B/s",
        'eta': "Unknown",
        'updated_at': datetime.now().isoformat()
    }

    # Start download in background
    async def download_task():
        try:
            # Get video info for title
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                info = await loop.run_in_executor(executor, get_video_info, request.url)

            title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(title)

            # Prepare output filename
            output_filename = f"{safe_title}.mp4"
            output_path = os.path.join(DOWNLOADS_DIR, output_filename)

            # Fallback download options - try 720p with different settings
            ydl_opts = {
                'format': 'best[height<=720]/best[height<=480]/best',
                'outtmpl': output_path,
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'extractor_retries': 5,
                'fragment_retries': 5,
                'retries': 5,
                'http_chunk_size': 1048576,
                'concurrent_fragment_downloads': 2,
                'sleep_interval': 2,
                'max_sleep_interval': 10,
                # Different user agent
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                # Try different extractor options
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash'],
                        'player_skip': ['configs'],
                        'player_client': ['android', 'web', 'ios'],
                    }
                },
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'merge_output_format': 'mp4',
                'prefer_ffmpeg': True,
            }

            def download_video_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Extract info first
                    info_dict = ydl.extract_info(request.url, download=False)
                    # Add download_id to info_dict
                    info_dict['_download_id'] = download_id
                    print(
                        f"🔍 Info extracted, starting fallback download with ID: {download_id}")

                    # Download with progress tracking
                    ydl.download([request.url])

            # Run download in thread pool
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, download_video_sync)

            # Check if file was downloaded successfully
            if os.path.exists(output_path):
                progress_data = {
                    'status': 'completed',
                    'progress': 100,
                    'filename': output_filename,
                    'file_path': output_path,
                    'updated_at': datetime.now().isoformat()
                }
                download_progress[download_id] = progress_data

                # Notify subscribers
                if download_id in progress_subscribers:
                    for queue in progress_subscribers[download_id]:
                        try:
                            queue.put_nowait(progress_data)
                        except:
                            pass

                print(f"✅ Fallback download completed: {output_filename}")
            else:
                raise Exception("File was not downloaded")

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Fallback download failed: {error_msg}")

            progress_data = {
                'status': 'failed',
                'error': error_msg,
                'updated_at': datetime.now().isoformat()
            }
            download_progress[download_id] = progress_data

            # Notify subscribers
            if download_id in progress_subscribers:
                for queue in progress_subscribers[download_id]:
                    try:
                        queue.put_nowait(progress_data)
                    except:
                        pass

    # Start the download task
    asyncio.create_task(download_task())

    # Return immediately with download ID
    return {
        "download_id": download_id,
        "message": "Fallback download started",
        "status": "downloading"
    }


@app.post("/download-alternative")
async def download_video_alternative(request: VideoInfoRequest):
    """Download video using alternative method with different extractors"""
    download_id = get_download_id(request.url, "alternative")

    print(f"⬇️ Starting alternative download: {request.url}")
    print(f"📋 Download ID: {download_id}")

    # Check if already downloading
    if download_id in download_progress:
        existing = download_progress[download_id]
        if existing['status'] in ['downloading']:
            return {
                "download_id": download_id,
                "message": "Download task already exists",
                "status": existing['status'],
                "progress": existing['progress']
            }

    # Initialize progress tracking
    download_progress[download_id] = {
        'status': 'downloading',
        'progress': 0,
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'speed': "0 B/s",
        'eta': "Unknown",
        'updated_at': datetime.now().isoformat()
    }

    # Start download in background
    async def download_task():
        try:
            # Get video info for title
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                info = await loop.run_in_executor(executor, get_video_info, request.url)

            title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(title)

            # Prepare output filename
            output_filename = f"{safe_title}.mp4"
            output_path = os.path.join(DOWNLOADS_DIR, output_filename)

            # Alternative download options - try different approach
            ydl_opts = {
                'format': 'best[height<=480]/best[height<=360]/best',
                'outtmpl': output_path,
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'extractor_retries': 3,
                'fragment_retries': 3,
                'retries': 3,
                'http_chunk_size': 1048576,
                'concurrent_fragment_downloads': 1,
                'sleep_interval': 3,
                'max_sleep_interval': 15,
                # Try different user agent
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                },
                # Try different extractor options
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_skip': ['configs'],
                        'player_client': ['android', 'web'],
                    }
                },
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'merge_output_format': 'mp4',
                'prefer_ffmpeg': True,
            }

            def download_video_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Extract info first
                    info_dict = ydl.extract_info(request.url, download=False)
                    # Add download_id to info_dict
                    info_dict['_download_id'] = download_id
                    print(
                        f"🔍 Info extracted, starting alternative download with ID: {download_id}")

                    # Download with progress tracking
                    ydl.download([request.url])

            # Run download in thread pool
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, download_video_sync)

            # Check if file was downloaded successfully
            if os.path.exists(output_path):
                progress_data = {
                    'status': 'completed',
                    'progress': 100,
                    'filename': output_filename,
                    'file_path': output_path,
                    'updated_at': datetime.now().isoformat()
                }
                download_progress[download_id] = progress_data

                # Notify subscribers
                if download_id in progress_subscribers:
                    for queue in progress_subscribers[download_id]:
                        try:
                            queue.put_nowait(progress_data)
                        except:
                            pass

                print(f"✅ Alternative download completed: {output_filename}")
            else:
                raise Exception("File was not downloaded")

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Alternative download failed: {error_msg}")

            progress_data = {
                'status': 'failed',
                'error': error_msg,
                'updated_at': datetime.now().isoformat()
            }
            download_progress[download_id] = progress_data

            # Notify subscribers
            if download_id in progress_subscribers:
                for queue in progress_subscribers[download_id]:
                    try:
                        queue.put_nowait(progress_data)
                    except:
                        pass

    # Start the download task
    asyncio.create_task(download_task())

    # Return immediately with download ID
    return {
        "download_id": download_id,
        "message": "Alternative download started",
        "status": "downloading"
    }

# Add a simple download method that tries multiple approaches


@app.post("/download-simple")
async def download_video_simple(request: VideoInfoRequest):
    """Download video using simple method with minimal options"""
    download_id = get_download_id(request.url, "simple")

    print(f"⬇️ Starting simple download: {request.url}")
    print(f"📋 Download ID: {download_id}")

    # Check if already downloading
    if download_id in download_progress:
        existing = download_progress[download_id]
        if existing['status'] in ['downloading']:
            return {
                "download_id": download_id,
                "message": "Download task already exists",
                "status": existing['status'],
                "progress": existing['progress']
            }

    # Initialize progress tracking
    download_progress[download_id] = {
        'status': 'downloading',
        'progress': 0,
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'speed': "0 B/s",
        'eta': "Unknown",
        'updated_at': datetime.now().isoformat()
    }

    # Start download in background
    async def download_task():
        try:
            # Get video info for title
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                info = await loop.run_in_executor(executor, get_video_info, request.url)

            title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(title)

            # Prepare output filename
            output_filename = f"{safe_title}.mp4"
            output_path = os.path.join(DOWNLOADS_DIR, output_filename)

            # Simple download options - minimal configuration
            ydl_opts = {
                'format': 'best[height<=720]+bestaudio/best[height<=720]/best',
                'outtmpl': output_path,
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'extractor_retries': 2,
                'fragment_retries': 2,
                'retries': 2,
                'http_chunk_size': 1048576,
                'concurrent_fragment_downloads': 1,
                'sleep_interval': 5,
                'max_sleep_interval': 20,
                # Minimal headers
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                },
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'merge_output_format': 'mp4',
                'prefer_ffmpeg': True,
            }

            def download_video_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Extract info first
                    info_dict = ydl.extract_info(request.url, download=False)
                    # Add download_id to info_dict
                    info_dict['_download_id'] = download_id
                    print(
                        f"🔍 Info extracted, starting simple download with ID: {download_id}")

                    # Download with progress tracking
                    ydl.download([request.url])

            # Run download in thread pool
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, download_video_sync)

            # Check if file was downloaded successfully
            if os.path.exists(output_path):
                progress_data = {
                    'status': 'completed',
                    'progress': 100,
                    'filename': output_filename,
                    'file_path': output_path,
                    'updated_at': datetime.now().isoformat()
                }
                download_progress[download_id] = progress_data

                # Notify subscribers
                if download_id in progress_subscribers:
                    for queue in progress_subscribers[download_id]:
                        try:
                            queue.put_nowait(progress_data)
                        except:
                            pass

                print(f"✅ Simple download completed: {output_filename}")
            else:
                raise Exception("File was not downloaded")

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Simple download failed: {error_msg}")

            progress_data = {
                'status': 'failed',
                'error': error_msg,
                'updated_at': datetime.now().isoformat()
            }
            download_progress[download_id] = progress_data

            # Notify subscribers
            if download_id in progress_subscribers:
                for queue in progress_subscribers[download_id]:
                    try:
                        queue.put_nowait(progress_data)
                    except:
                        pass

    # Start the download task
    asyncio.create_task(download_task())

    # Return immediately with download ID
    return {
        "download_id": download_id,
        "message": "Simple download started",
        "status": "downloading"
    }


@app.get("/download-progress/{download_id}")
async def get_download_progress_stream(download_id: str):
    """Stream download progress in real-time using Server-Sent Events"""
    print(f"📊 Progress stream request for: {download_id}")

    async def event_generator():
        # Create a queue for this subscriber
        import asyncio
        queue = asyncio.Queue()

        # Add to subscribers
        if download_id not in progress_subscribers:
            progress_subscribers[download_id] = []
        progress_subscribers[download_id].append(queue)

        try:
            # Send initial progress if available
            if download_id in download_progress:
                initial_progress = download_progress[download_id]
                yield f"data: {json.dumps(initial_progress)}\n\n"

            # Stream updates
            while True:
                try:
                    # Wait for progress update
                    progress_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(progress_data)}\n\n"

                    # If completed or failed, break
                    if progress_data['status'] in ['completed', 'failed', 'cancelled']:
                        break

                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f"data: {json.dumps({'status': 'keepalive'})}\n\n"

        finally:
            # Remove from subscribers
            if download_id in progress_subscribers:
                try:
                    progress_subscribers[download_id].remove(queue)
                except:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )


@app.delete("/downloads/{download_id}")
async def cancel_download(download_id: str):
    """Cancel or delete a download"""
    print(f" Cancelling download: {download_id}")

    if download_id in download_progress:
        progress_data = {
            'status': 'cancelled',
            'updated_at': datetime.now().isoformat()
        }
        download_progress[download_id] = progress_data

        # Notify subscribers
        if download_id in progress_subscribers:
            for queue in progress_subscribers[download_id]:
                try:
                    queue.put_nowait(progress_data)
                except:
                    pass

        print(f"✅ Download cancelled: {download_id}")
        return {"message": "Download cancelled successfully"}
    else:
        raise HTTPException(status_code=404, detail="Download not found")


@app.get("/")
async def root():
    return {"message": "YouTube Downloader API is running"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting YouTube Downloader API server...")
    print("📡 Server will be available at: http://localhost:8000")
    print("📋 API docs available at: http://localhost:8000/docs")
    print(f"📁 Downloads will be saved to: {DOWNLOADS_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
