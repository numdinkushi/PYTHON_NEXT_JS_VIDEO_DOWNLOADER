import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.services.download_service import DownloadService

router = APIRouter()
download_service = DownloadService()


@router.get("/download-progress/{download_id}")
async def get_download_progress_stream(download_id: str):
    """Stream download progress in real-time using Server-Sent Events"""
    print(f"📊 Progress stream request for: {download_id}")

    async def event_generator():
        # Create a queue for this subscriber
        queue = asyncio.Queue()

        # Add to subscribers
        if download_id not in download_service.progress_subscribers:
            download_service.progress_subscribers[download_id] = []
        download_service.progress_subscribers[download_id].append(queue)

        try:
            # Send initial progress if available
            if download_id in download_service.download_progress:
                initial_progress = download_service.download_progress[download_id]
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
            if download_id in download_service.progress_subscribers:
                try:
                    download_service.progress_subscribers[download_id].remove(queue)
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


@router.delete("/downloads/{download_id}")
async def cancel_download(download_id: str):
    """Cancel or delete a download"""
    print(f"🚫 Cancelling download: {download_id}")

    if download_service.cancel_download(download_id):
        return {"message": "Download cancelled successfully"}
    else:
        raise HTTPException(status_code=404, detail="Download not found")
