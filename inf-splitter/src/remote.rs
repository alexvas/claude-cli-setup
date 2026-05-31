use std::sync::Arc;

use axum::body::Body;
use axum::http::{header, HeaderMap};
use axum::response::Response;
use bytes::Bytes;
use futures::StreamExt;
use reqwest::Client;

use crate::config::Config;
use crate::error::AppError;

#[derive(Clone)]
pub struct RemoteHandler {
    client: Client,
    upstream_base: String,
}

impl RemoteHandler {
    pub fn new(config: Arc<Config>) -> Self {
        Self {
            client: Client::builder()
                .build()
                .expect("reqwest client"),
            upstream_base: config.deepseek_anthropic_base_url.clone(),
        }
    }

    pub async fn handle(
        &self,
        body: Bytes,
        request_headers: &HeaderMap,
    ) -> Result<Response, AppError> {
        let url = format!("{}/v1/messages", self.upstream_base);
        let mut builder = self.client.post(url);

        for (name, value) in request_headers.iter() {
            if should_forward_request_header(name.as_str()) {
                if let Ok(value) = value.to_str() {
                    builder = builder.header(name.as_str(), value);
                }
            }
        }

        let upstream = builder.body(body).send().await?;
        let status = upstream.status();
        let response_headers = copy_response_headers(upstream.headers());

        if is_event_stream(upstream.headers()) {
            let stream = upstream.bytes_stream().map(|chunk| {
                chunk.map_err(|err| std::io::Error::other(err.to_string()))
            });
            let mut response = Response::builder().status(status);
            for (name, value) in &response_headers {
                response = response.header(name.as_str(), value.as_str());
            }
            if !response_headers
                .iter()
                .any(|(name, _)| name.eq_ignore_ascii_case("content-type"))
            {
                response = response.header(header::CONTENT_TYPE, "text/event-stream");
            }
            if !response_headers
                .iter()
                .any(|(name, _)| name.eq_ignore_ascii_case("cache-control"))
            {
                response = response.header(header::CACHE_CONTROL, "no-cache");
            }
            if !response_headers
                .iter()
                .any(|(name, _)| name.eq_ignore_ascii_case("connection"))
            {
                response = response.header(header::CONNECTION, "keep-alive");
            }
            return response
                .body(Body::from_stream(stream))
                .map_err(|err| AppError::Internal(err.to_string()));
        }

        let body = upstream.bytes().await?;
        let mut response = Response::builder().status(status);
        for (name, value) in response_headers {
            response = response.header(name, value);
        }
        response
            .body(Body::from(body))
            .map_err(|err| AppError::Internal(err.to_string()))
    }
}

fn should_forward_request_header(name: &str) -> bool {
    !matches!(
        name.to_ascii_lowercase().as_str(),
        "host"
            | "connection"
            | "content-length"
            | "transfer-encoding"
            | "te"
            | "trailers"
            | "upgrade"
            | "keep-alive"
    )
}

fn is_event_stream(headers: &HeaderMap) -> bool {
    headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(|value| value.contains("text/event-stream"))
        .unwrap_or(false)
}

fn copy_response_headers(headers: &HeaderMap) -> Vec<(String, String)> {
    headers
        .iter()
        .filter_map(|(name, value)| {
            let name = name.as_str();
            if matches!(
                name,
                "content-type"
                    | "request-id"
                    | "anthropic-ratelimit-requests-limit"
                    | "anthropic-ratelimit-requests-remaining"
                    | "anthropic-ratelimit-requests-reset"
                    | "anthropic-ratelimit-tokens-limit"
                    | "anthropic-ratelimit-tokens-remaining"
                    | "anthropic-ratelimit-tokens-reset"
            ) {
                value
                    .to_str()
                    .ok()
                    .map(|v| (name.to_string(), v.to_string()))
            } else {
                None
            }
        })
        .collect()
}
