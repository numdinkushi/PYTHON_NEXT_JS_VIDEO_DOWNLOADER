from pydantic import BaseModel
from typing import List, Optional


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


class DownloadResponse(BaseModel):
    download_id: str
    message: str
    status: str
    progress: Optional[float] = None


class ProgressData(BaseModel):
    status: str
    progress: float
    downloaded_bytes: int
    total_bytes: int
    speed: str
    eta: str
    updated_at: str
    filename: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None
