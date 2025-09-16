import hashlib
import re
from datetime import datetime


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
