from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, HOST, PORT, DOWNLOADS_DIR
from app.api import video_info, download, progress, download_quality

app = FastAPI(title="YouTube Downloader API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video_info.router, tags=["video-info"])
app.include_router(download.router, tags=["download"])
app.include_router(progress.router, tags=["progress"])
app.include_router(download_quality.router, tags=["download-quality"])


@app.get("/")
async def root():
    return {"message": "YouTube Downloader API is running"}


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting YouTube Downloader API server...")
    print("📡 Server will be available at: http://localhost:8000")
    print("📋 API docs available at: http://localhost:8000/docs")
    print(f"📁 Downloads will be saved to: {DOWNLOADS_DIR}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
