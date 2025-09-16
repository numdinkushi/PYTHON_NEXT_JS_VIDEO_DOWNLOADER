'use client';

import { useState, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Download, Loader2, AlertCircle, CheckCircle, Play, Clock, FileVideo, Zap, RefreshCw, X, Pause, Play as PlayIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";

interface VideoInfo {
  title: string;
  duration: string;
  thumbnail: string;
  formats: Array<{
    format_id: string;
    ext: string;
    resolution: string;
    filesize?: number;
    vcodec: string;
    acodec: string;
  }>;
}

interface DownloadProgress {
  status: 'downloading' | 'completed' | 'error' | 'exists' | 'failed' | 'paused' | 'cancelled';
  percentage?: number;
  filename?: string;
  error?: string;
  download_id?: string;
  message?: string;
  speed?: string;
  eta?: string;
}

export default function YouTubeDownloader() {
  const [url, setUrl] = useState('');
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('');
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [error, setError] = useState('');

  // Real-time progress tracking with EventSource
  useEffect(() => {
    if (downloadProgress?.download_id && downloadProgress.status === 'downloading') {
      console.log('Starting real-time progress stream for:', downloadProgress.download_id);

      const eventSource = new EventSource(`http://localhost:8000/download-progress/${downloadProgress.download_id}`);

      eventSource.onmessage = (event) => {
        try {
          const progressData = JSON.parse(event.data);
          console.log('Received progress update:', progressData);

          if (progressData.status === 'keepalive') {
            return; // Ignore keepalive messages
          }

          setDownloadProgress({
            status: progressData.status === 'failed' ? 'error' : progressData.status,
            percentage: progressData.progress,
            download_id: progressData.download_id || downloadProgress.download_id,
            filename: progressData.filename,
            error: progressData.error,
            speed: progressData.speed,
            eta: progressData.eta
          });

          if (progressData.status === 'completed') {
            eventSource.close();
          } else if (progressData.status === 'failed') {
            eventSource.close();
          } else if (progressData.status === 'cancelled') {
            eventSource.close();
            setDownloadProgress(null);
          }
        } catch (err) {
          console.error('Error parsing progress data:', err);
        }
      };

      eventSource.onerror = (err) => {
        console.error('EventSource error:', err);
        eventSource.close();
      };

      return () => {
        eventSource.close();
      };
    }
  }, [downloadProgress?.download_id]);

  const fetchVideoInfo = async () => {
    if (!url) {
      setError('Please enter a YouTube URL');
      return;
    }

    setLoading(true);
    setError('');
    setVideoInfo(null);

    try {
      const response = await fetch('/api/video-info', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch video information');
      }

      const data = await response.json();
      setVideoInfo(data);
    } catch (err) {
      setError('Failed to fetch video information. Please check the URL and try again.');
    } finally {
      setLoading(false);
    }
  };

  const downloadVideo = async () => {
    if (!selectedFormat || !videoInfo) return;

    setDownloadProgress({ status: 'downloading', percentage: 0 });

    try {
      const response = await fetch('/api/download', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url,
          format_id: selectedFormat
        }),
      });

      const data = await response.json();

      if (data.message === 'Download task already exists') {
        setDownloadProgress({
          status: 'exists',
          message: 'Download task already exists',
          download_id: data.download_id,
          percentage: data.progress
        });
        return;
      }

      if (data.status === 'failed') {
        setDownloadProgress({
          status: 'error',
          error: data.error || 'Download failed',
          download_id: data.download_id
        });
        return;
      }

      if (data.download_id) {
        setDownloadProgress({
          status: 'downloading',
          download_id: data.download_id,
          percentage: 0
        });
      }
    } catch (err) {
      setDownloadProgress({
        status: 'error',
        error: 'Download failed. Please try again.'
      });
    }
  };

  const cancelDownload = async (downloadId: string) => {
    try {
      console.log('Cancelling download:', downloadId);
      const response = await fetch(`http://localhost:8000/downloads/${downloadId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setDownloadProgress(null);
        console.log('Download cancelled successfully');
      } else {
        console.error('Failed to cancel download');
      }
    } catch (err) {
      console.error('Error cancelling download:', err);
    }
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'Unknown size';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    if (bytes === 0) return '0 Byte';
    const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)).toString());
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  };

  const getQualityColor = (resolution: string) => {
    if (resolution.includes('2160') || resolution.includes('4K')) return 'bg-purple-100 text-purple-800 border-purple-200';
    if (resolution.includes('1440')) return 'bg-blue-100 text-blue-800 border-blue-200';
    if (resolution.includes('1080')) return 'bg-green-100 text-green-800 border-green-200';
    if (resolution.includes('720')) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    if (resolution.includes('480')) return 'bg-orange-100 text-orange-800 border-orange-200';
    return 'bg-gray-100 text-gray-800 border-gray-200';
  };

  // Add fallback download function
  const downloadFallback = async () => {
    if (!videoInfo) return;

    setDownloadProgress({ status: 'downloading', percentage: 0 });

    try {
      const response = await fetch('/api/download-fallback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();

      if (data.download_id) {
        setDownloadProgress({
          status: 'downloading',
          download_id: data.download_id,
          percentage: 0
        });
      }
    } catch (err) {
      setDownloadProgress({
        status: 'error',
        error: 'Download failed. Please try again.'
      });
    }
  };

  // Add multiple download functions
  const downloadAlternative = async () => {
    if (!videoInfo) return;

    setDownloadProgress({ status: 'downloading', percentage: 0 });

    try {
      const response = await fetch('/api/download-alternative', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();

      if (data.download_id) {
        setDownloadProgress({
          status: 'downloading',
          download_id: data.download_id,
          percentage: 0
        });
      }
    } catch (err) {
      setDownloadProgress({
        status: 'error',
        error: 'Download failed. Please try again.'
      });
    }
  };

  const downloadSimple = async () => {
    if (!videoInfo) return;

    setDownloadProgress({ status: 'downloading', percentage: 0 });

    try {
      const response = await fetch('/api/download-simple', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();

      if (data.download_id) {
        setDownloadProgress({
          status: 'downloading',
          download_id: data.download_id,
          percentage: 0
        });
      }
    } catch (err) {
      setDownloadProgress({
        status: 'error',
        error: 'Download failed. Please try again.'
      });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      {/* Header */}
      <div className="container mx-auto py-12 px-4 max-w-6xl">
        <div className="text-center mb-12">
          <div className="flex items-center justify-center mb-6">
            <div className="p-3 bg-gradient-to-r from-red-500 to-pink-500 rounded-2xl shadow-lg">
              <Play className="w-8 h-8 text-white" />
            </div>
          </div>
          <h1 className="text-5xl font-bold bg-gradient-to-r from-gray-900 via-blue-900 to-purple-900 bg-clip-text text-transparent mb-4">
            YouTube Video Downloader
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Download YouTube videos in various formats and resolutions with lightning-fast speed
          </p>
        </div>

        {/* URL Input Card */}
        <Card className="mb-8 shadow-xl border-0 bg-white/80 backdrop-blur-sm">
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Zap className="w-6 h-6 text-blue-600" />
              Enter YouTube URL
            </CardTitle>
            <CardDescription className="text-lg">
              Paste the YouTube video URL to get started
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex gap-3">
              <Input
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && fetchVideoInfo()}
                className="h-12 text-lg border-2 focus:border-blue-500 transition-colors"
              />
              <Button
                onClick={fetchVideoInfo}
                disabled={loading}
                className="h-12 px-8 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white font-semibold shadow-lg hover:shadow-xl transition-all duration-200"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin mr-2" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Play className="w-5 h-5 mr-2" />
                    Get Info
                  </>
                )}
              </Button>
            </div>

            {error && (
              <Alert variant="destructive" className="border-red-200 bg-red-50">
                <AlertCircle className="h-5 w-5" />
                <AlertDescription className="text-red-800 font-medium">{error}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Video Info Card */}
        {videoInfo && (
          <Card className="mb-8 shadow-xl border-0 bg-white/90 backdrop-blur-sm">
            <CardHeader className="pb-6">
              <CardTitle className="flex items-start gap-6">
                <div className="relative">
                  <img
                    src={videoInfo.thumbnail}
                    alt="Video thumbnail"
                    className="w-48 h-36 object-cover rounded-xl shadow-lg"
                  />
                  <div className="absolute inset-0 bg-black/20 rounded-xl flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                    <Play className="w-12 h-12 text-white" />
                  </div>
                </div>
                <div className="flex-1">
                  <h2 className="text-2xl font-bold mb-3 text-gray-900 leading-tight">
                    {videoInfo.title}
                  </h2>
                  <div className="flex items-center gap-4">
                    <Badge variant="secondary" className="px-3 py-1 text-sm">
                      <Clock className="w-4 h-4 mr-1" />
                      {videoInfo.duration}
                    </Badge>
                    <Badge variant="outline" className="px-3 py-1 text-sm">
                      <FileVideo className="w-4 h-4 mr-1" />
                      {videoInfo.formats.length} formats
                    </Badge>
                  </div>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <label className="text-lg font-semibold mb-4 block text-gray-800">
                  Select Format and Quality
                </label>
                <Select value={selectedFormat} onValueChange={setSelectedFormat}>
                  <SelectTrigger className="h-14 text-lg border-2 focus:border-blue-500">
                    <SelectValue placeholder="Choose format and quality" />
                  </SelectTrigger>
                  <SelectContent className="max-h-80">
                    {videoInfo.formats.map((format) => (
                      <SelectItem key={format.format_id} value={format.format_id} className="py-3">
                        <div className="flex justify-between items-center w-full">
                          <div className="flex items-center gap-3">
                            <Badge className={`px-2 py-1 text-xs font-semibold ${getQualityColor(format.resolution)}`}>
                              {format.resolution}
                            </Badge>
                            <span className="font-medium text-gray-800">
                              {format.ext.toUpperCase()}
                            </span>
                          </div>
                          <span className="text-sm text-gray-500 ml-4">
                            {formatFileSize(format.filesize)}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-3">
                <Button
                  onClick={downloadVideo}
                  disabled={!selectedFormat || downloadProgress?.status === 'downloading'}
                  className="w-full h-14 text-lg bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white font-bold shadow-lg hover:shadow-xl transition-all duration-200"
                >
                  {downloadProgress?.status === 'downloading' ? (
                    <>
                      <Loader2 className="w-6 h-6 mr-3 animate-spin" />
                      Downloading Video...
                    </>
                  ) : (
                    <>
                      <Download className="w-6 h-6 mr-3" />
                      Download Selected Quality
                    </>
                  )}
                </Button>

                <Button
                  onClick={downloadAlternative}
                  disabled={!videoInfo || downloadProgress?.status === 'downloading'}
                  className="w-full h-12 text-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold shadow-lg hover:shadow-xl transition-all duration-200"
                >
                  <Download className="w-5 h-5 mr-2" />
                  Download Alternative (480p)
                </Button>

                <Button
                  onClick={downloadFallback}
                  disabled={!videoInfo || downloadProgress?.status === 'downloading'}
                  className="w-full h-12 text-lg bg-gradient-to-r from-orange-600 to-red-600 hover:from-orange-700 hover:to-red-700 text-white font-bold shadow-lg hover:shadow-xl transition-all duration-200"
                >
                  <Download className="w-5 h-5 mr-2" />
                  Download Fallback (720p)
                </Button>

                <Button
                  onClick={downloadSimple}
                  disabled={!videoInfo || downloadProgress?.status === 'downloading'}
                  className="w-full h-12 text-lg bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-bold shadow-lg hover:shadow-xl transition-all duration-200"
                >
                  <Download className="w-5 h-5 mr-2" />
                  Download Simple (Lowest Quality)
                </Button>
              </div>

              {/* Download Progress */}
              {downloadProgress && (
                <div className="mt-6 space-y-4">
                  {downloadProgress.status === 'downloading' && (
                    <Card className="border-blue-200 bg-blue-50">
                      <CardContent className="pt-6">
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-blue-800 font-medium">Downloading...</span>
                            <span className="text-blue-600 text-sm">{downloadProgress.percentage?.toFixed(1)}%</span>
                          </div>
                          <Progress value={downloadProgress.percentage || 0} className="h-2" />
                          <div className="flex justify-between items-center">
                            <div className="text-xs text-blue-600">
                              {downloadProgress.speed && (
                                <span>Speed: {downloadProgress.speed}</span>
                              )}
                              {downloadProgress.eta && (
                                <span className="ml-2">ETA: {downloadProgress.eta}</span>
                              )}
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => downloadProgress.download_id && cancelDownload(downloadProgress.download_id)}
                              className="text-red-600 border-red-200 hover:bg-red-50"
                            >
                              <X className="w-4 h-4 mr-1" />
                              Cancel
                            </Button>
                          </div>
                          <div className="text-xs text-blue-600 text-center">
                            Files saved to ~/Downloads/youtube_videos
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {downloadProgress.status === 'exists' && (
                    <Alert className="border-yellow-200 bg-yellow-50">
                      <AlertCircle className="h-5 w-5 text-yellow-600" />
                      <AlertDescription className="text-yellow-800 font-medium">
                        {downloadProgress.message} - Progress: {downloadProgress.percentage?.toFixed(1)}%
                      </AlertDescription>
                    </Alert>
                  )}

                  {downloadProgress.status === 'completed' && (
                    <Alert className="border-green-200 bg-green-50">
                      <CheckCircle className="h-5 w-5 text-green-600" />
                      <AlertDescription className="text-green-800 font-medium">
                        🎉 Download completed successfully! File saved to ~/Downloads/youtube_videos
                      </AlertDescription>
                    </Alert>
                  )}

                  {downloadProgress.status === 'error' && (
                    <Alert variant="destructive" className="border-red-200 bg-red-50">
                      <AlertCircle className="h-5 w-5" />
                      <AlertDescription className="text-red-800 font-medium">
                        {downloadProgress.error}
                        {downloadProgress.download_id && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => downloadVideo()}
                            className="ml-3 text-green-600 border-green-200 hover:bg-green-50"
                          >
                            <RefreshCw className="w-4 h-4 mr-1" />
                            Retry
                          </Button>
                        )}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <div className="text-center mt-16">
          <p className="text-gray-500 text-sm">
            Made with ❤️ for fast and reliable YouTube video downloads
          </p>
        </div>
      </div>
    </div>
  );
}
