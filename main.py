from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import vtracer
import json
import logging
from typing import Optional
import os
import asyncio
import multiprocessing
import time
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE_MB = 10
CONVERSION_TIMEOUT_SECONDS = float(os.getenv("CONVERSION_TIMEOUT_SECONDS", 30))
MAX_CONCURRENT_CONVERSIONS = int(os.getenv("MAX_CONCURRENT_CONVERSIONS", 4))
POLL_INTERVAL_SECONDS = 0.05

# Each conversion runs in its own process so it can be killed on timeout or when the
# client goes away. A thread cannot be stopped: timed-out and abandoned conversions used
# to keep burning CPU and a pool slot until vtracer finished on its own.
# fork is cheap here (vtracer is already imported) and is the Linux default on 3.12.
mp_context = multiprocessing.get_context(
    "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
)
conversion_slots = asyncio.Semaphore(MAX_CONCURRENT_CONVERSIONS)

# vtracer silently treats unknown color modes as "color"
COLOR_MODE_ALIASES = {"bw": "binary"}


class ClientDisconnected(Exception):
    pass


def _convert_in_child(conn, image_bytes, vtracer_options):
    try:
        conn.send(("ok", vtracer.convert_raw_image_to_svg(image_bytes, **vtracer_options)))
    except Exception as e:
        conn.send(("error", f"{e}\n{traceback.format_exc()}"))
    finally:
        conn.close()


async def _acquire_slot(request: Request):
    """Waits for a free conversion slot, giving up if the client leaves meanwhile."""
    while True:
        try:
            await asyncio.wait_for(conversion_slots.acquire(), timeout=0.25)
            return
        except asyncio.TimeoutError:
            if await request.is_disconnected():
                raise ClientDisconnected()


async def run_conversion(request: Request, image_bytes: bytes, vtracer_options: dict) -> str:
    """Runs vtracer in a child process, killing it on timeout or client disconnect."""
    await _acquire_slot(request)
    parent_conn, child_conn = mp_context.Pipe(duplex=False)
    process = mp_context.Process(
        target=_convert_in_child, args=(child_conn, image_bytes, vtracer_options), daemon=True
    )
    try:
        process.start()
        child_conn.close()
        started = time.monotonic()
    except Exception:
        parent_conn.close()
        child_conn.close()
        conversion_slots.release()
        raise

    try:

        while True:
            # Read as soon as data arrives: the child blocks on send until the pipe drains
            if parent_conn.poll():
                status, payload = parent_conn.recv()
                if status == "error":
                    raise RuntimeError(payload)
                return payload
            if not process.is_alive():
                raise RuntimeError(f"Converter process exited unexpectedly (code {process.exitcode})")
            if time.monotonic() - started > CONVERSION_TIMEOUT_SECONDS:
                raise asyncio.TimeoutError()
            if await request.is_disconnected():
                raise ClientDisconnected()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        if process.is_alive():
            process.kill()
        process.join(timeout=1)
        parent_conn.close()
        conversion_slots.release()

app = FastAPI(
    title="VTracer API",
    description="Convert raster images to SVG using VTracer",
    version="1.0.2"
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
    request: Request,
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
                color_mode = options_dict.get("color_mode", "color")
                vtracer_options = {
                    "colormode": COLOR_MODE_ALIASES.get(color_mode, color_mode),
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
        
        try:
            svg_bytes = await run_conversion(request, image_bytes, vtracer_options)
        except ClientDisconnected:
            logger.info(f"Client disconnected, conversion cancelled: {image.filename}")
            # 499 (nginx's "client closed request"); nobody is left to read it
            return Response(status_code=499)
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