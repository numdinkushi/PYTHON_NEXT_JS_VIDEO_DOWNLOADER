import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const { url, format_id } = await request.json()
    
    if (!url || !format_id) {
      return NextResponse.json(
        { error: 'URL and format_id are required' }, 
        { status: 400 }
      )
    }

    // Call Python backend for download
    const response = await fetch('http://localhost:8000/download', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url, format_id }),
    })

    if (!response.ok) {
      throw new Error('Download failed')
    }

    // Stream the file back to the client
    const blob = await response.blob()
    
    return new NextResponse(blob, {
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="video.${format_id.split('-')[1] || 'mp4'}"`,
      },
    })
  } catch (error) {
    console.error('Download error:', error)
    return NextResponse.json(
      { error: 'Download failed' },
      { status: 500 }
    )
  }
}
