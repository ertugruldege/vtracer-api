use std::net::SocketAddr;
use std::process::Command;
use std::path::Path;

use axum::{
    extract::{DefaultBodyLimit, Multipart, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use tower_http::{cors::CorsLayer, trace::TraceLayer};
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, EnvFilter};
use uuid::Uuid;

#[derive(Clone)]
struct AppState {}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug, Deserialize, Serialize, Default)]
struct ConvertOptions {
    #[serde(default = "default_color_mode")] 
    color_mode: String,
    #[serde(default = "default_hierarchical")] 
    hierarchical: String,
    #[serde(default)]
    filter_speckle: Option<u32>,
    #[serde(default)]
    corner_threshold: Option<u32>,
    #[serde(default)]
    color_precision: Option<u32>,
    #[serde(default)]
    gradient_step: Option<u32>,
    #[serde(default = "default_mode")] 
    mode: String,
    #[serde(default)]
    path_precision: Option<u32>,
    #[serde(default)]
    preset: Option<String>,
    #[serde(default)]
    segment_length: Option<u32>,
    #[serde(default)]
    splice_threshold: Option<f32>,
}

fn default_color_mode() -> String { "color".to_string() }
fn default_hierarchical() -> String { "stacked".to_string() }
fn default_mode() -> String { "spline".to_string() }

#[derive(Serialize)]
struct ConvertResponse {
    success: bool,
    svg_content: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));
    fmt::Subscriber::builder().with_env_filter(filter).init();

    let state = AppState {};

    let app = Router::new()
        .route("/api/health", get(health))
        .route("/api/convert", post(convert))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .layer(DefaultBodyLimit::max(10 * 1024 * 1024))
        .with_state(state);

    let port: u16 = std::env::var("PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(8080);
    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    info!("listening on {}", addr);
    axum::Server::bind(&addr).serve(app.into_make_service()).await?;
    Ok(())
}

async fn health() -> impl IntoResponse {
    (StatusCode::OK, Json(HealthResponse { status: "ok" }))
}

async fn convert(State(_state): State<AppState>, mut multipart: Multipart) -> impl IntoResponse {
    let mut options: ConvertOptions = ConvertOptions::default();
    let mut image_bytes: Option<Vec<u8>> = None;
    let mut file_extension: Option<String> = None;

    while let Some(field) = multipart.next_field().await.unwrap_or(None) {
        let name = field.name().unwrap_or("").to_string();
        if name == "options" {
            if let Ok(text) = field.text().await {
                if let Ok(parsed) = serde_json::from_str::<ConvertOptions>(&text) {
                    options = parsed;
                }
            }
        } else if name == "image" {
            match field.bytes().await {
                Ok(b) => {
                    image_bytes = Some(b.to_vec());
                    if let Some(filename) = field.file_name() {
                        file_extension = Path::new(filename)
                            .extension()
                            .and_then(|ext| ext.to_str())
                            .map(|s| s.to_lowercase());
                    }
                },
                Err(e) => {
                    error!(error = %e, "failed to read image bytes");
                    return Response::builder()
                        .status(StatusCode::BAD_REQUEST)
                        .body("invalid image upload".into())
                        .unwrap();
                }
            }
        }
    }

    let image_bytes = match image_bytes {
        Some(bytes) => bytes,
        None => {
            return Response::builder()
                .status(StatusCode::BAD_REQUEST)
                .body("'image' field (multipart) gereklidir".into())
                .unwrap();
        }
    };

    // Dosya boyutu kontrolü (40MB limit)
    if image_bytes.len() > 40 * 1024 * 1024 {
        return Response::builder()
            .status(StatusCode::BAD_REQUEST)
            .body("Dosya çok büyük. Maksimum 10MB desteklenir.".into())
            .unwrap();
    }

    // Geçici dosyalar için UUID oluştur
    let temp_id = Uuid::new_v4();
    let input_ext = file_extension.unwrap_or_else(|| "png".to_string());
    let input_path = format!("/tmp/input_{}.{}", temp_id, input_ext);
    let output_path = format!("/tmp/output_{}.svg", temp_id);

    // Geçici dizin oluştur
    if let Err(e) = tokio::fs::create_dir_all("/tmp").await {
        error!(error = %e, "failed to create temp directory");
        return Response::builder()
            .status(StatusCode::INTERNAL_SERVER_ERROR)
            .body("Geçici dizin oluşturulamadı".into())
            .unwrap();
    }

    // Input dosyasını yaz
    if let Err(e) = tokio::fs::write(&input_path, &image_bytes).await {
        error!(error = %e, "failed to write input file");
        return Response::builder()
            .status(StatusCode::INTERNAL_SERVER_ERROR)
            .body("Input dosyası yazılamadı".into())
            .unwrap();
    }

    // Vtracer komutunu çalıştır
    let result = run_vtracer(&input_path, &output_path, &options).await;

    // Geçici dosyaları temizle
    let _ = tokio::fs::remove_file(&input_path).await;
    let _ = tokio::fs::remove_file(&output_path).await;

    match result {
        Ok(svg_content) => {
            let resp = ConvertResponse { 
                success: true, 
                svg_content 
            };
            (StatusCode::OK, Json(resp)).into_response()
        }
        Err(e) => {
            error!(error = %e, "vtracer conversion failed");
            Response::builder()
                .status(StatusCode::INTERNAL_SERVER_ERROR)
                .body(format!("Dönüştürme hatası: {}", e).into())
                .unwrap()
        }
    }
}

async fn run_vtracer(input_path: &str, output_path: &str, options: &ConvertOptions) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let mut cmd = Command::new("vtracer");
    
    cmd.arg("--input").arg(input_path)
       .arg("--output").arg(output_path)
       .arg("--colormode").arg(&options.color_mode)
       .arg("--hierarchical").arg(&options.hierarchical)
       .arg("--filter_speckle").arg(options.filter_speckle.unwrap_or(2).to_string())
       .arg("--corner_threshold").arg(options.corner_threshold.unwrap_or(60).to_string())
       .arg("--color_precision").arg(options.color_precision.unwrap_or(8).to_string())
       .arg("--gradient_step").arg(options.gradient_step.unwrap_or(0).to_string())
       .arg("--mode").arg(&options.mode)
       .arg("--path_precision").arg(options.path_precision.unwrap_or(1).to_string())
       .arg("--segment_length").arg(options.segment_length.unwrap_or(8).to_string())
       .arg("--splice_threshold").arg(options.splice_threshold.unwrap_or(2.5).to_string());

    if let Some(preset) = &options.preset {
        cmd.arg("--preset").arg(preset);
    }

    info!("Running vtracer command: {:?}", cmd);

    let output = cmd.output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        error!("vtracer failed: {}", stderr);
        return Err(format!("vtracer failed: {}", stderr).into());
    }

    let svg_content = tokio::fs::read_to_string(output_path).await?;
    Ok(svg_content)
}
