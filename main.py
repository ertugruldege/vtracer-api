from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import vtracer
import json
import logging
from typing import Optional
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VTracer API",
    description="Convert raster images to SVG using VTracer",
    version="1.0.0"
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
    
    # Check file size (40MB limit)
    image_bytes = await image.read()
    if len(image_bytes) > 40 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum 40MB supported."
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
                    "filter_speckle": options_dict.get("filter_speckle", 2),
                    "corner_threshold": options_dict.get("corner_threshold", 60),
                    "color_precision": options_dict.get("color_precision", 8),
                    "gradient_step": options_dict.get("gradient_step", 0),
                    "mode": options_dict.get("mode", "spline"),
                    "path_precision": options_dict.get("path_precision", 1),
                    "segment_length": options_dict.get("segment_length", 8),
                    "splice_threshold": options_dict.get("splice_threshold", 2.5),
                }
                
                # Add preset if provided
                if "preset" in options_dict and options_dict["preset"]:
                    vtracer_options["preset"] = options_dict["preset"]
                    
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in options parameter")
        
        logger.info(f"Converting image: {image.filename}, size: {len(image_bytes)} bytes")
        
        # Convert using vtracer
        svg_bytes = vtracer.convert_raw_image_to_svg(image_bytes, **vtracer_options)
        
        logger.info(f"Conversion successful, SVG size: {len(svg_bytes)} bytes")
        
        # Return SVG response
        return Response(
            content=svg_bytes, 
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f"attachment; filename={image.filename.rsplit('.', 1)[0]}.svg"
            }
        )
        
    except Exception as e:
        logger.error(f"Conversion failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Conversion failed: {str(e)}"
        )

@app.get("/api/models")
async def get_models():
    """Get available vtracer models/presets"""
    return {
        "presets": ["bw", "poster", "photo"],
        "color_modes": ["color", "bw"],
        "hierarchical_modes": ["stacked", "cutout"],
        "curve_modes": ["pixel", "polygon", "spline"]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
