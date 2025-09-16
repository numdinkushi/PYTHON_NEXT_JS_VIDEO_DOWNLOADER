from fastapi import APIRouter, HTTPException
from app.models.schemas import VideoInfoRequest, DownloadResponse
from app.services.download_service import download_service

router = APIRouter()


@router.post("/download-simple", response_model=DownloadResponse)
async def download_video_simple(request: VideoInfoRequest):
    """Download video using simple method with audio"""
    try:
        download_id = await download_service.download_video_simple(request.url)
        return DownloadResponse(
            download_id=download_id,
            message="Simple download started",
            status="downloading"
        )
    except Exception as e:
        print(f"❌ Error starting download: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
