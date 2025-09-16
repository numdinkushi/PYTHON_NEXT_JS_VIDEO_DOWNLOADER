from fastapi import APIRouter, HTTPException
from app.models.schemas import VideoInfoRequest, VideoInfo
from app.services.download_service import DownloadService

router = APIRouter()
download_service = DownloadService()


@router.post("/video-info", response_model=VideoInfo)
async def get_video_info(request: VideoInfoRequest):
    """Get video information and available formats"""
    try:
        return await download_service.get_video_info_async(request.url)
    except Exception as e:
        print(f"❌ Error extracting video info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
