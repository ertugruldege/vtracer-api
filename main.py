from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import vtracer
import json
import logging
from typing import Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Thread pool for vtracer conversion (CPU-bound operation)
executor = ThreadPoolExecutor(max_workers=4)

# Configuration
MAX_FILE_SIZE_MB = 10
CONVERSION_TIMEOUT_SECONDS = 30

app = FastAPI(
    title="VTracer API",
    description="Convert raster images to SVG using VTracer",
    version="1.0.1"
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint returns API information"""
    return {
        "message": "Welcome to the VTracer API!",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "convert": "/api/convert"
        }
    }

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "vtracer-api"}

@app.post("/api/convert")
async def convert_image(
    image: UploadFile = File(...),
    options: Optional[str] = Form(None)
):
    """Convert an uploaded image to SVG using vtracer"""
    
    # Validate file type
    allowed_types = [
        "image/png", "image/jpeg", "image/jpg", 
        "image/webp", "image/tiff", "image/bmp", "image/gif"
    ]
    
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type: {image.content_type}. Allowed types: {allowed_types}"
        )
    
    # Check file size (10MB limit)
    image_bytes = await image.read()
    file_size_mb = len(image_bytes) / (1024 * 1024)
    
    if len(image_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        logger.warning(f"File too large rejected: {image.filename}, size: {file_size_mb:.2f}MB")
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum {MAX_FILE_SIZE_MB}MB supported. Your file: {file_size_mb:.2f}MB"
        )
    
    try:
        # Parse options if provided
        vtracer_options = {}
        if options:
            try:
                options_dict = json.loads(options)
                vtracer_options = {
                    "colormode": options_dict.get("color_mode", "color"),
                    "hierarchical": options_dict.get("hierarchical", "stacked"),
                    "mode": options_dict.get("mode", "spline"),
                    "filter_speckle": options_dict.get("filter_speckle", 4),
                    "color_precision": options_dict.get("color_precision", 6),
                    "layer_difference": options_dict.get("layer_difference", 16),
                    "corner_threshold": options_dict.get("corner_threshold", 60),
                    "length_threshold": options_dict.get("segment_length", 4.0),
                    "max_iterations": options_dict.get("max_iterations", 10),
                    "splice_threshold": options_dict.get("splice_threshold", 45),
                    "path_precision": options_dict.get("path_precision", 3),
                }
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in options parameter for {image.filename}")
        
        logger.info(f"Starting conversion: {image.filename}, size: {file_size_mb:.2f}MB, content_type: {image.content_type}")
        
        # Convert using vtracer with timeout
        loop = asyncio.get_event_loop()
        try:
            svg_bytes = await asyncio.wait_for(
                loop.run_in_executor(
                    executor,
                    lambda: vtracer.convert_raw_image_to_svg(image_bytes, **vtracer_options)
                ),
                timeout=CONVERSION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(f"Conversion timeout after {CONVERSION_TIMEOUT_SECONDS}s: {image.filename}, size: {file_size_mb:.2f}MB")
            raise HTTPException(
                status_code=504,
                detail=f"Conversion timeout. Image may be too complex. Try a smaller or simpler image."
            )
        
        logger.info(f"Conversion successful: {image.filename}, input: {file_size_mb:.2f}MB, output: {len(svg_bytes)} bytes")
        
        # Return SVG response
        return Response(
            content=svg_bytes,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f"attachment; filename={image.filename.rsplit('.', 1)[0]}.svg"
            }
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (like timeout) without wrapping
        raise
        
    except Exception as e:
        # Log detailed error information
        logger.error(
            f"Conversion failed: {image.filename}, "
            f"size: {file_size_mb:.2f}MB, "
            f"content_type: {image.content_type}, "
            f"error: {str(e)}"
        )
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Conversion failed: {str(e)}"
        )

@app.get("/api/models")
async def get_models():
    """Get available vtracer models/presets"""
    return {
        "presets": ["bw", "poster", "photo"],
        "color_modes": ["color", "binary"],
        "hierarchical_modes": ["stacked", "cutout"],
        "curve_modes": ["spline", "polygon", "none"]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)