mod config;
mod error;
mod local;
mod remote;
mod router;

use std::sync::Arc;

use router::{router, AppState};
use tracing::info;
use tracing_subscriber::EnvFilter;

use crate::config::Config;
use crate::local::LocalHandler;
use crate::remote::RemoteHandler;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive("inf_splitter=info".parse()?))
        .init();

    let config = Arc::new(Config::from_env().map_err(|err| {
        eprintln!("configuration error: {err}");
        err
    })?);

    info!(
        listen = %config.listen_addr,
        ollama = %config.ollama_base_url,
        deepseek = %config.deepseek_anthropic_base_url,
        local_models = ?config.local_models,
        "starting inf-splitter"
    );

    let local = LocalHandler::new(config.as_ref())?;
    let remote = RemoteHandler::new(config.clone());
    let state = AppState {
        config: config.clone(),
        local,
        remote,
    };

    let app = router(state);
    let listener = tokio::net::TcpListener::bind(config.listen_addr).await?;
    info!(addr = %config.listen_addr, "listening");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        use tokio::signal::unix::{signal, SignalKind};
        signal(SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => info!("received Ctrl+C, shutting down"),
        _ = terminate => info!("received SIGTERM, shutting down"),
    }
}
