from fastapi import APIRouter, HTTPException
from app.models.schemas import VideoInfoRequest, DownloadResponse
from app.services.download_service import download_service

router = APIRouter()


@router.post("/download-1080p", response_model=DownloadResponse)
async def download_video_1080p(request: VideoInfoRequest):
    """Download video in 1080p quality"""
    try:
        download_id = await download_service.download_video_quality(request.url, "1080p")
        return DownloadResponse(
            download_id=download_id,
            message="1080p download started",
            status="downloading"
        )
    except Exception as e:
        print(f"❌ Error starting 1080p download: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-720p", response_model=DownloadResponse)
async def download_video_720p(request: VideoInfoRequest):
    """Download video in 720p quality"""
    try:
        download_id = await download_service.download_video_quality(request.url, "720p")
        return DownloadResponse(
            download_id=download_id,
            message="720p download started",
            status="downloading"
        )
    except Exception as e:
        print(f"❌ Error starting 720p download: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-480p", response_model=DownloadResponse)
async def download_video_480p(request: VideoInfoRequest):
    """Download video in 480p quality"""
    try:
        download_id = await download_service.download_video_quality(request.url, "480p")
        return DownloadResponse(
            download_id=download_id,
            message="480p download started",
            status="downloading"
        )
    except Exception as e:
        print(f"❌ Error starting 480p download: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-360p", response_model=DownloadResponse)
async def download_video_360p(request: VideoInfoRequest):
    """Download video in 360p quality"""
    try:
        download_id = await download_service.download_video_quality(request.url, "360p")
        return DownloadResponse(
            download_id=download_id,
            message="360p download started",
            status="downloading"
        )
    except Exception as e:
        print(f"❌ Error starting 360p download: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
