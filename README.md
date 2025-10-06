# vtracer-api

An Axum-based API service with real vtracer CLI integration. Converts raster images (PNG, JPG, JPEG, WebP, TIFF, BMP, GIF) into vector SVG.

## Endpoints

-   `GET /api/health` — health check
-   `POST /api/convert` — multipart form-data: `image` (file), `options` (JSON string)

## Supported Formats

-   PNG, JPG, JPEG, WebP, TIFF, BMP, GIF
-   Maximum file size: 40MB

## Options Parameters

```json
{
    "color_mode": "color|bw",
    "hierarchical": "stacked|cutout",
    "filter_speckle": 2,
    "corner_threshold": 60,
    "color_precision": 8,
    "gradient_step": 0,
    "mode": "pixel|polygon|spline",
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

# Convert raster to SVG
curl -X POST http://localhost:8080/api/convert \
  -F image=@/path/to/image.jpg \
  -F 'options={"color_mode":"color","mode":"spline","corner_threshold":45}'
```

## Run Locally

```bash
# Development
cargo run

# Production build
cargo build --release
./target/release/vtracer-api
```

## Nixpacks Deployment

`nixpacks.toml` is included. You can point Coolify to this folder as the source and deploy directly.

### Environment Variables

-   `PORT`: Server port (default: 8080)
-   `RUST_LOG`: Log level (default: info)

## Technical Notes

-   Axum web framework (Rust)
-   Async/await
-   Temporary file handling with automatic cleanup
-   Comprehensive error handling
-   Invokes the `vtracer` CLI with all supported parameters
