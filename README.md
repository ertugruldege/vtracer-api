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
  "color_mode": "color|bw",
  "hierarchical": "stacked|cutout",
  "filter_speckle": 2,
  "corner_threshold": 60,
  "color_precision": 8,
  "gradient_step": 0,
  "mode": "spline",
  "path_precision": 1,
  "preset": "bw|poster|photo",
  "segment_length": 8,
  "splice_threshold": 2.5
}
```

## Examples

```bash
# Health check
curl http://localhost:8080/api/health

# Convert image to SVG
curl -X POST http://localhost:8080/api/convert \
  -F image=@/path/to/image.jpg \
  -F 'options={"color_mode":"color","mode":"spline","corner_threshold":45}'

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
- VTracer Python library integration
- Automatic file type validation
- Comprehensive error handling
- CORS enabled for web integration
- Async/await support
