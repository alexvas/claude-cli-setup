use std::collections::HashSet;
use std::env;
use std::net::SocketAddr;

use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DockerNetworkMode {
    Rootful,
    Rootless,
}

impl DockerNetworkMode {
    fn parse(raw: &str) -> Result<Self, ConfigError> {
        match raw.trim().to_ascii_lowercase().as_str() {
            "rootful" => Ok(Self::Rootful),
            "rootless" => Ok(Self::Rootless),
            other => Err(ConfigError::InvalidDockerNetworkMode(other.to_string())),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    pub listen_addr: SocketAddr,
    pub local_models: HashSet<String>,
    pub ollama_base_url: String,
    pub deepseek_anthropic_base_url: String,
    pub omit_stream_options: bool,
    pub remote_model_ids: Vec<String>,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("invalid LISTEN_ADDR: {0}")]
    ListenAddr(String),
    #[error("invalid DOCKER_NETWORK_MODE: {0} (expected rootful or rootless)")]
    InvalidDockerNetworkMode(String),
    #[error("DOCKER_NETWORK_MODE=rootless requires EXTERNAL_IP or SOCKS_HOST (or set OLLAMA_BASE_URL explicitly)")]
    RootlessHostMissing,
    #[error("LOCAL_MODELS must contain at least one model")]
    LocalModelsEmpty,
    #[error("environment error: {0}")]
    Env(#[from] env::VarError),
}

impl Config {
    pub fn from_env() -> Result<Self, ConfigError> {
        let listen_addr = parse_listen_addr()?;
        let local_models = parse_local_models()?;
        let ollama_base_url = resolve_ollama_base_url()?;
        let deepseek_anthropic_base_url = env::var("DEEPSEEK_ANTHROPIC_BASE_URL")
            .unwrap_or_else(|_| "https://api.deepseek.com/anthropic".to_string())
            .trim_end_matches('/')
            .to_string();
        let omit_stream_options = env_truthy("OMIT_STREAM_OPTIONS");
        let remote_model_ids = parse_remote_model_ids();

        Ok(Self {
            listen_addr,
            local_models,
            ollama_base_url,
            deepseek_anthropic_base_url,
            omit_stream_options,
            remote_model_ids,
        })
    }

    pub fn is_local_model(&self, model: &str) -> bool {
        self.local_models.contains(model)
    }

    /// Deterministic, lexicographically sorted union of local and remote model ids.
    pub fn sorted_model_ids(&self) -> Vec<String> {
        let mut ids: Vec<String> = self.local_models.iter().cloned().collect();
        for model in &self.remote_model_ids {
            if !self.local_models.contains(model) {
                ids.push(model.clone());
            }
        }
        ids.sort();
        ids
    }
}

fn parse_listen_addr() -> Result<SocketAddr, ConfigError> {
    if let Ok(raw) = env::var("LISTEN_ADDR") {
        return raw
            .parse()
            .map_err(|err| ConfigError::ListenAddr(format!("{raw}: {err}")));
    }

    let port = env::var("PROXY_PORT")
        .or_else(|_| env::var("LISTEN_PORT"))
        .unwrap_or_else(|_| "3000".to_string());
    format!("0.0.0.0:{port}")
        .parse()
        .map_err(|err| ConfigError::ListenAddr(format!("0.0.0.0:{port}: {err}")))
}

fn parse_local_models() -> Result<HashSet<String>, ConfigError> {
    let raw = env::var("LOCAL_MODELS").unwrap_or_else(|_| "gemma4:31b".to_string());
    let models: HashSet<String> = raw
        .split(',')
        .map(str::trim)
        .filter(|model| !model.is_empty())
        .map(str::to_string)
        .collect();

    if models.is_empty() {
        return Err(ConfigError::LocalModelsEmpty);
    }

    Ok(models)
}

fn parse_remote_model_ids() -> Vec<String> {
    env::var("REMOTE_MODEL_IDS")
        .unwrap_or_else(|_| {
            "deepseek-v4-pro[1m],deepseek-v4-flash,deepseek-chat,deepseek-reasoner".to_string()
        })
        .split(',')
        .map(str::trim)
        .filter(|model| !model.is_empty())
        .map(str::to_string)
        .collect()
}

pub fn resolve_ollama_base_url() -> Result<String, ConfigError> {
    if let Ok(url) = env::var("OLLAMA_BASE_URL") {
        let trimmed = url.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.trim_end_matches('/').to_string());
        }
    }

    let port = env::var("OLLAMA_PORT").unwrap_or_else(|_| "11434".to_string());
    let mode = DockerNetworkMode::parse(
        &env::var("DOCKER_NETWORK_MODE").unwrap_or_else(|_| "rootful".to_string()),
    )?;

    let host = match mode {
        DockerNetworkMode::Rootful => "host.docker.internal".to_string(),
        DockerNetworkMode::Rootless => resolve_rootless_host()?,
    };

    Ok(format!("http://{host}:{port}"))
}

fn resolve_rootless_host() -> Result<String, ConfigError> {
    if let Ok(ip) = env::var("EXTERNAL_IP") {
        let trimmed = ip.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }

    // Deprecated alias kept for backward compatibility during migration.
    if let Ok(ip) = env::var("OLLAMA_HOST_IP") {
        let trimmed = ip.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }

    if let Ok(host) = env::var("SOCKS_HOST") {
        let trimmed = host.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }

    Err(ConfigError::RootlessHostMissing)
}

fn env_truthy(name: &str) -> bool {
    match env::var(name) {
        Ok(value) => matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        ),
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Mutex, OnceLock};

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .unwrap_or_else(|err| err.into_inner())
    }

    fn clear_ollama_env() {
        for key in [
            "OLLAMA_BASE_URL",
            "DOCKER_NETWORK_MODE",
            "EXTERNAL_IP",
            "OLLAMA_HOST_IP",
            "SOCKS_HOST",
            "OLLAMA_PORT",
        ] {
            env::remove_var(key);
        }
    }

    #[test]
    fn rootful_defaults_to_host_docker_internal() {
        let _guard = env_lock();
        clear_ollama_env();
        env::set_var("DOCKER_NETWORK_MODE", "rootful");

        let url = resolve_ollama_base_url().expect("rootful url");
        assert_eq!(url, "http://host.docker.internal:11434");
    }

    #[test]
    fn rootless_prefers_external_ip() {
        let _guard = env_lock();
        clear_ollama_env();
        env::set_var("DOCKER_NETWORK_MODE", "rootless");
        env::set_var("EXTERNAL_IP", "10.0.0.5");
        env::set_var("SOCKS_HOST", "10.0.0.9");

        let url = resolve_ollama_base_url().expect("rootless url");
        assert_eq!(url, "http://10.0.0.5:11434");
    }

    #[test]
    fn rootless_falls_back_to_socks_host() {
        let _guard = env_lock();
        clear_ollama_env();
        env::set_var("DOCKER_NETWORK_MODE", "rootless");
        env::set_var("SOCKS_HOST", "192.168.1.100");

        let url = resolve_ollama_base_url().expect("rootless socks fallback");
        assert_eq!(url, "http://192.168.1.100:11434");
    }

    #[test]
    fn rootless_without_host_fails_fast() {
        let _guard = env_lock();
        clear_ollama_env();
        env::set_var("DOCKER_NETWORK_MODE", "rootless");

        let err = resolve_ollama_base_url().expect_err("missing host");
        assert!(matches!(err, ConfigError::RootlessHostMissing));
    }

    #[test]
    fn ollama_base_url_override_wins() {
        let _guard = env_lock();
        clear_ollama_env();
        env::set_var("OLLAMA_BASE_URL", "http://custom:9999/");
        env::set_var("DOCKER_NETWORK_MODE", "rootless");

        let url = resolve_ollama_base_url().expect("override url");
        assert_eq!(url, "http://custom:9999");
    }
}
