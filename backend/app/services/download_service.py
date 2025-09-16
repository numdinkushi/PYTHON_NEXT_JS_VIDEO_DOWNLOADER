import yt_dlp
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any

from app.core.config import DOWNLOADS_DIR, YT_DLP_OPTIONS
from app.models.schemas import VideoFormat, VideoInfo
from app.utils.helpers import (
    get_download_id, sanitize_filename, format_duration, 
    get_resolution_string, format_speed, format_eta
)


class DownloadService:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DownloadService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.download_progress: Dict[str, Dict[str, Any]] = {}
            self.progress_subscribers: Dict[str, list] = {}
            DownloadService._initialized = True

    def get_video_info(self, url: str) -> dict:
        """Extract video information using yt-dlp"""
        ydl_opts = YT_DLP_OPTIONS.copy()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return info
            except Exception as e:
                raise Exception(f"Failed to extract video info: {str(e)}")

    def progress_hook(self, d):
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

            progress = (downloaded_bytes / total_bytes * 100) if total_bytes > 0 else 0

            progress_data = {
                'status': 'downloading',
                'progress': min(progress, 100),
                'downloaded_bytes': downloaded_bytes,
                'total_bytes': total_bytes,
                'speed': format_speed(speed) if speed else "0 B/s",
                'eta': format_eta(eta),
                'updated_at': datetime.now().isoformat()
            }

            self.download_progress[download_id] = progress_data
            self._notify_subscribers(download_id, progress_data)
            print(f"📊 [{download_id[:8]}] {progress:.1f}% - {format_speed(speed) if speed else '0 B/s'} - ETA: {format_eta(eta)}")

        elif d['status'] == 'finished':
            progress_data = {
                'status': 'completed',
                'progress': 100,
                'updated_at': datetime.now().isoformat()
            }
            self.download_progress[download_id] = progress_data
            self._notify_subscribers(download_id, progress_data)
            print(f"✅ [{download_id[:8]}] Download completed")

        elif d['status'] == 'error':
            progress_data = {
                'status': 'failed',
                'error': str(d.get('error', 'Unknown error')),
                'updated_at': datetime.now().isoformat()
            }
            self.download_progress[download_id] = progress_data
            self._notify_subscribers(download_id, progress_data)
            print(f"❌ [{download_id[:8]}] Download failed: {d.get('error', 'Unknown error')}")

    def _notify_subscribers(self, download_id: str, progress_data: dict):
        """Notify all subscribers of progress updates"""
        if download_id in self.progress_subscribers:
            for queue in self.progress_subscribers[download_id]:
                try:
                    queue.put_nowait(progress_data)
                except:
                    pass

    async def get_video_info_async(self, url: str) -> VideoInfo:
        """Get video information and available formats"""
        print(f"🔍 Received video info request for: {url}")
        
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            info = await loop.run_in_executor(executor, self.get_video_info, url)

        print(f"✅ Successfully extracted info for: {info.get('title', 'Unknown')}")

        formats = []
        seen_formats = set()

        # Get all available formats
        all_formats = info.get('formats', [])
        
        # Create quality options based on available heights
        available_heights = set()
        for f in all_formats:
            if f.get('height') and f.get('vcodec') != 'none':
                available_heights.add(f.get('height'))

        # Create format options for common qualities
        quality_options = [
            {'height': 1080, 'label': '1080p'},
            {'height': 720, 'label': '720p'},
            {'height': 480, 'label': '480p'},
            {'height': 360, 'label': '360p'},
            {'height': 240, 'label': '240p'},
        ]

        for quality in quality_options:
            height = quality['height']
            if height in available_heights:
                # Find the best format for this quality
                best_format = None
                for f in all_formats:
                    if (f.get('height') == height and 
                        f.get('vcodec') != 'none' and 
                        f.get('ext') in ['mp4', 'webm']):
                        if not best_format or f.get('filesize', 0) > best_format.get('filesize', 0):
                            best_format = f

                if best_format:
                    resolution = get_resolution_string(best_format)
                    formats.append(VideoFormat(
                        format_id=f"best[height<={height}]",
                        ext=best_format.get('ext', 'mp4'),
                        resolution=resolution,
                        filesize=best_format.get('filesize'),
                        vcodec=best_format.get('vcodec', 'unknown'),
                        acodec='bestaudio'  # Will be merged during download
                    ))

        # If no specific qualities found, add the best available
        if not formats:
            for f in all_formats:
                if f.get('vcodec') != 'none' and f.get('ext') in ['mp4', 'webm']:
                    resolution = get_resolution_string(f)
                    formats.append(VideoFormat(
                        format_id=f['format_id'],
                        ext=f.get('ext', 'mp4'),
                        resolution=resolution,
                        filesize=f.get('filesize'),
                        vcodec=f.get('vcodec', 'unknown'),
                        acodec='bestaudio'
                    ))
                    break

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

        print(f"📋 Found {len(formats)} video format options")
        for fmt in formats:
            print(f"   - {fmt.resolution} {fmt.ext.upper()} - {fmt.vcodec}")

        return VideoInfo(
            title=info.get('title', 'Unknown Title'),
            duration=format_duration(info.get('duration')),
            thumbnail=info.get('thumbnail', ''),
            formats=formats
        )

    async def download_video_simple(self, url: str) -> str:
        """Download video using simple method with audio"""
        download_id = get_download_id(url, "simple")
        
        print(f"⬇️ Starting simple download: {url}")
        print(f"📋 Download ID: {download_id}")

        # Check if already downloading
        if download_id in self.download_progress:
            existing = self.download_progress[download_id]
            if existing['status'] in ['downloading']:
                return download_id

        # Initialize progress tracking
        self.download_progress[download_id] = {
            'status': 'downloading',
            'progress': 0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'speed': "0 B/s",
            'eta': "Unknown",
            'updated_at': datetime.now().isoformat()
        }

        # Start download in background
        asyncio.create_task(self._download_task_simple(url, download_id))
        return download_id

    async def _download_task_simple(self, url: str, download_id: str):
        """Background task for simple download"""
        try:
            # Get video info for title
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                info = await loop.run_in_executor(executor, self.get_video_info, url)

            title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(title)

            # Prepare output filename
            output_filename = f"{safe_title}.mp4"
            output_path = os.path.join(DOWNLOADS_DIR, output_filename)

            # Simple download options with audio
            ydl_opts = {
                'format': 'best[height<=1080]+bestaudio/best[height<=720]+bestaudio/best[height<=480]+bestaudio/best',
                'outtmpl': output_path,
                'progress_hooks': [self.progress_hook],
                'quiet': False,
                'no_warnings': False,
                'extractor_retries': 2,
                'fragment_retries': 2,
                'retries': 2,
                'http_chunk_size': 1048576,
                'concurrent_fragment_downloads': 1,
                'sleep_interval': 5,
                'max_sleep_interval': 20,
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
                    info_dict = ydl.extract_info(url, download=False)
                    info_dict['_download_id'] = download_id
                    print(f"🔍 Info extracted, starting simple download with ID: {download_id}")
                    ydl.download([url])

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
                self.download_progress[download_id] = progress_data
                self._notify_subscribers(download_id, progress_data)
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
            self.download_progress[download_id] = progress_data
            self._notify_subscribers(download_id, progress_data)

    async def download_video_quality(self, url: str, quality: str) -> str:
        """Download video with specific quality"""
        download_id = get_download_id(url, quality)
        
        print(f"⬇️ Starting {quality} download: {url}")
        print(f"📋 Download ID: {download_id}")

        # Check if already downloading
        if download_id in self.download_progress:
            existing = self.download_progress[download_id]
            if existing['status'] in ['downloading']:
                return download_id

        # Initialize progress tracking
        self.download_progress[download_id] = {
            'status': 'downloading',
            'progress': 0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'speed': "0 B/s",
            'eta': "Unknown",
            'updated_at': datetime.now().isoformat()
        }

        # Start download in background
        asyncio.create_task(self._download_task_quality(url, download_id, quality))
        return download_id

    async def _download_task_quality(self, url: str, download_id: str, quality: str):
        """Background task for quality-specific download"""
        try:
            # Get video info for title
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                info = await loop.run_in_executor(executor, self.get_video_info, url)

            title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(title)

            # Prepare output filename
            output_filename = f"{safe_title}_{quality}.mp4"
            output_path = os.path.join(DOWNLOADS_DIR, output_filename)

            # Quality-specific format selection
            if quality == "1080p":
                format_selector = "best[height<=1080]+bestaudio/best[height<=1080]/best"
            elif quality == "720p":
                format_selector = "best[height<=720]+bestaudio/best[height<=720]/best"
            elif quality == "480p":
                format_selector = "best[height<=480]+bestaudio/best[height<=480]/best"
            elif quality == "360p":
                format_selector = "best[height<=360]+bestaudio/best[height<=360]/best"
            else:
                format_selector = "best+bestaudio/best"

            # Download options with quality-specific format
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_path,
                'progress_hooks': [self.progress_hook],
                'quiet': False,
                'no_warnings': False,
                'extractor_retries': 3,
                'fragment_retries': 3,
                'retries': 3,
                'http_chunk_size': 1048576,
                'concurrent_fragment_downloads': 1,
                'sleep_interval': 2,
                'max_sleep_interval': 10,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
                    info_dict = ydl.extract_info(url, download=False)
                    info_dict['_download_id'] = download_id
                    print(f"🔍 Info extracted, starting {quality} download with ID: {download_id}")
                    ydl.download([url])

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
                self.download_progress[download_id] = progress_data
                self._notify_subscribers(download_id, progress_data)
                print(f"✅ {quality} download completed: {output_filename}")
            else:
                raise Exception("File was not downloaded")

        except Exception as e:
            error_msg = str(e)
            print(f"❌ {quality} download failed: {error_msg}")

            progress_data = {
                'status': 'failed',
                'error': error_msg,
                'updated_at': datetime.now().isoformat()
            }
            self.download_progress[download_id] = progress_data
            self._notify_subscribers(download_id, progress_data)

    def get_download_progress(self, download_id: str) -> dict:
        """Get current download progress"""
        return self.download_progress.get(download_id, {})

    def cancel_download(self, download_id: str) -> bool:
        """Cancel a download"""
        if download_id in self.download_progress:
            progress_data = {
                'status': 'cancelled',
                'updated_at': datetime.now().isoformat()
            }
            self.download_progress[download_id] = progress_data
            self._notify_subscribers(download_id, progress_data)
            print(f"✅ Download cancelled: {download_id}")
            return True
        return False


# Create singleton instance
download_service = DownloadService()
