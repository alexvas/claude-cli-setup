use anyllm_client::{Auth, Client, ClientConfig, ClientError, HttpClientConfig};
use anyllm_translate::anthropic::{MessageCreateRequest, StreamEvent};
use anyllm_translate::mapping::streaming_map::StreamingTranslator;
use anyllm_translate::openai::ChatCompletionChunk;
use anyllm_translate::{translate_request, translate_response, TranslationConfig};
use axum::body::Body;
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use futures::StreamExt;
use reqwest::Client as HttpClient;

use crate::config::Config;
use crate::error::AppError;

#[derive(Clone)]
pub struct LocalHandler {
    client: Client,
    http: HttpClient,
    backend_url: String,
    translation: TranslationConfig,
    omit_stream_options: bool,
}

impl LocalHandler {
    pub fn new(config: &Config) -> Result<Self, AppError> {
        let backend_url = format!("{}/v1/chat/completions", config.ollama_base_url);
        let mut translation = TranslationConfig::builder();
        for model in &config.local_models {
            translation = translation.model_map(model, model);
        }

        let mut http = HttpClientConfig::default();
        http.ssrf_protection = false;

        let client_config = ClientConfig::builder()
            .backend_url(backend_url.clone())
            .auth(Auth::Bearer("ollama".into()))
            .http(http)
            .translation(translation.build())
            .build();

        Ok(Self {
            client: Client::new(client_config),
            http: HttpClient::builder()
                .build()
                .map_err(|err| AppError::Internal(err.to_string()))?,
            backend_url,
            translation: {
                let mut builder = TranslationConfig::builder();
                for model in &config.local_models {
                    builder = builder.model_map(model, model);
                }
                builder.build()
            },
            omit_stream_options: config.omit_stream_options,
        })
    }

    pub async fn handle(
        &self,
        body: &[u8],
        request_headers: &HeaderMap,
    ) -> Result<Response, AppError> {
        let req: MessageCreateRequest = serde_json::from_slice(body)?;
        if req.stream.unwrap_or(false) {
            self.handle_stream(&req, request_headers).await
        } else if self.omit_stream_options {
            self.handle_sync_manual(&req).await
        } else {
            self.handle_sync_client(&req).await
        }
    }

    async fn handle_sync_client(&self, req: &MessageCreateRequest) -> Result<Response, AppError> {
        let response = self.client.messages(req).await?;
        Ok((StatusCode::OK, axum::Json(response)).into_response())
    }

    async fn handle_sync_manual(&self, req: &MessageCreateRequest) -> Result<Response, AppError> {
        let mut openai_req = translate_request(req, &self.translation)
            .map_err(|err| AppError::Upstream(err.to_string()))?;
        openai_req.stream_options = None;

        let (openai_resp, _, _) = self.client.chat_completion(&openai_req).await?;
        let response = translate_response(&openai_resp, &req.model);
        Ok((StatusCode::OK, axum::Json(response)).into_response())
    }

    async fn handle_stream(
        &self,
        req: &MessageCreateRequest,
        request_headers: &HeaderMap,
    ) -> Result<Response, AppError> {
        if self.omit_stream_options {
            self.handle_stream_manual(req, request_headers).await
        } else {
            self.handle_stream_client(req, request_headers).await
        }
    }

    async fn handle_stream_client(
        &self,
        req: &MessageCreateRequest,
        request_headers: &HeaderMap,
    ) -> Result<Response, AppError> {
        let (stream, _rate_limits) = self.client.messages_stream(req).await?;
        Ok(sse_response(
            request_headers,
            stream.map(|event| {
                event
                    .map(|stream_event| format_sse_event(&stream_event))
                    .map_err(|err| std::io::Error::other(err.to_string()))
            }),
        )?)
    }

    async fn handle_stream_manual(
        &self,
        req: &MessageCreateRequest,
        request_headers: &HeaderMap,
    ) -> Result<Response, AppError> {
        let mut openai_req = translate_request(req, &self.translation)
            .map_err(|err| AppError::Upstream(err.to_string()))?;
        openai_req.stream = Some(true);
        openai_req.stream_options = None;

        let upstream = self
            .http
            .post(&self.backend_url)
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::AUTHORIZATION, "Bearer ollama")
            .json(&openai_req)
            .send()
            .await?;

        if !upstream.status().is_success() {
            let status = upstream.status();
            let body = upstream.text().await.unwrap_or_default();
            return Err(AppError::Upstream(format!("HTTP {status}: {body}")));
        }

        let model = req.model.clone();
        let byte_stream = upstream.bytes_stream().map(|chunk| {
            chunk.map_err(|err| std::io::Error::other(err.to_string()))
        });

        let sse_stream = futures::stream::unfold(
            (byte_stream, StreamingTranslator::new(model), String::new()),
            |(mut byte_stream, mut translator, mut buffer)| async move {
                loop {
                    if let Some(line_end) = buffer.find('\n') {
                        let line = buffer[..line_end].trim_end_matches('\r').to_string();
                        buffer = buffer[line_end + 1..].to_string();
                        if let Some(events) = parse_sse_line(&line, &mut translator) {
                            let payload = events
                                .iter()
                                .map(format_sse_event_str)
                                .collect::<String>();
                            return Some((
                                Ok(bytes::Bytes::from(payload)),
                                (byte_stream, translator, buffer),
                            ));
                        }
                        continue;
                    }

                    match byte_stream.next().await {
                        Some(Ok(chunk)) => {
                            buffer.push_str(&String::from_utf8_lossy(&chunk));
                        }
                        Some(Err(err)) => {
                            return Some((Err(err), (byte_stream, translator, buffer)));
                        }
                        None => {
                            let payload = translator
                                .finish()
                                .iter()
                                .map(format_sse_event_str)
                                .collect::<String>();
                            if payload.is_empty() {
                                return None;
                            }
                            return Some((
                                Ok(bytes::Bytes::from(payload)),
                                (byte_stream, translator, buffer),
                            ));
                        }
                    }
                }
            },
        );

        sse_response(request_headers, sse_stream)
    }
}

fn parse_sse_line(line: &str, translator: &mut StreamingTranslator) -> Option<Vec<StreamEvent>> {
    let data = line.strip_prefix("data: ")?.trim();
    if data == "[DONE]" {
        return Some(translator.finish());
    }
    let chunk: ChatCompletionChunk = serde_json::from_str(data).ok()?;
    Some(translator.process_chunk(&chunk))
}

fn sse_response<S>(request_headers: &HeaderMap, body: S) -> Result<Response, AppError>
where
    S: futures::Stream<Item = Result<bytes::Bytes, std::io::Error>> + Send + 'static,
{
    let accept = request_headers
        .get(header::ACCEPT)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("text/event-stream");

    Ok(Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "text/event-stream")
        .header(header::CACHE_CONTROL, "no-cache")
        .header(header::CONNECTION, "keep-alive")
        .header(header::ACCEPT, accept)
        .body(Body::from_stream(body))
        .map_err(|err| AppError::Internal(err.to_string()))?)
}

fn format_sse_event_str(event: &StreamEvent) -> String {
    let payload = serde_json::to_string(event).unwrap_or_else(|_| "{}".to_string());
    format!("event: message\ndata: {payload}\n\n")
}

fn format_sse_event(event: &StreamEvent) -> bytes::Bytes {
    bytes::Bytes::from(format_sse_event_str(event))
}

impl From<anyllm_client::ClientError> for AppError {
    fn from(err: ClientError) -> Self {
        Self::Upstream(err.to_string())
    }
}
