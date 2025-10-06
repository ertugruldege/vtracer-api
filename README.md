# vtracer-api

A FastAPI-based API service with VTracer integration. Converts raster images (PNG, JPG, JPEG, WebP, TIFF, BMP, GIF) into vector SVG.

## Endpoints

- `GET /` — API information
- `GET /api/health` — health check
- `POST /api/convert` — convert image to SVG
- `GET /api/models` — available models/presets

## Supported Formats

- PNG, JPG, JPEG, WebP, TIFF, BMP, GIF
- Maximum file size: 40MB

## Convert Endpoint

**POST** `/api/convert`

**Form Data:**

- `image`: Image file (required)
- `options`: JSON string with conversion options (optional)

**Options Parameters:**

```json
{
  "color_mode": "color|binary",
  "hierarchical": "stacked|cutout",
  "mode": "spline|polygon|none",
  "filter_speckle": 4,
  "color_precision": 6,
  "layer_difference": 16,
  "corner_threshold": 60,
  "segment_length": 4.0,
  "max_iterations": 10,
  "splice_threshold": 45,
  "path_precision": 3
}
```

**Parameter Details:**

- `color_mode`: `"color"` for multicolor SVG, `"binary"` for black & white
- `hierarchical`: `"stacked"` for layered approach, `"cutout"` for shape cutting
- `mode`: `"spline"` for smooth curves, `"polygon"` for angular shapes, `"none"` for no smoothing
- `filter_speckle`: Remove small noise pixels (default: 4)
- `color_precision`: Color quantization precision (default: 6)
- `layer_difference`: Layer separation threshold (default: 16)
- `corner_threshold`: Corner detection sensitivity (default: 60)
- `segment_length`: Minimum path segment length (default: 4.0)
- `max_iterations`: Maximum optimization iterations (default: 10)
- `splice_threshold`: Path splicing threshold (default: 45)
- `path_precision`: Path simplification precision (default: 3)

## Examples

```bash
# Health check
curl http://localhost:8080/api/health

# Convert image to SVG with default settings
curl -X POST http://localhost:8080/api/convert \
  -F image=@/path/to/image.jpg

# Convert with custom options
curl -X POST http://localhost:8080/api/convert \
  -F image=@/path/to/image.jpg \
  -F 'options={"color_mode":"binary","mode":"polygon","corner_threshold":45}'

# Get available models
curl http://localhost:8080/api/models
```

## Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python main.py

# Or with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## Nixpacks Deployment

`nixpacks.toml` is included. You can point Coolify to this folder as the source and deploy directly.

### Environment Variables

- `PORT`: Server port (default: 8080)
- `PYTHONUNBUFFERED`: Set to "1" for proper logging

## Technical Notes

- FastAPI web framework (Python)
- VTracer Python library integration (v0.6.11)
- Automatic file type validation
- Comprehensive error handling
- CORS enabled for web integration
- Async/await support
- Based on official VTracer documentation from [PyPI](https://pypi.org/project/vtracer/)
