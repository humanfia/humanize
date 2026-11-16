//! WebSocket carriers: a `ws://` or `wss://` route, whose binary messages carry the bytes
//! (Section 3.4.6 of [WIRE]), and a native join through a relay, spliced once joined (Section
//! 5.5 of [WIRE]). `wss` trusts what the system trusts, and is never what makes a carrier
//! trusted: mutual TLS runs inside it all the same.

use std::sync::Arc;

use futures_util::{SinkExt, StreamExt};
use rustls::ClientConfig;
use rustls_pki_types::ServerName;
use rustls_platform_verifier::BuilderVerifierExt;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio_tungstenite::WebSocketStream;
use tokio_tungstenite::tungstenite::Message;
use url::Url;

use super::{Stream, tls};

/// The most bytes one binary message carries: well under the relay's 1 MiB.
const CHUNK: usize = 1 << 14;

/// A WebSocket opened on `url`.
pub async fn open(url: &str) -> Result<WebSocketStream<Stream>, String> {
    let failed = |why: &dyn std::fmt::Display| format!("{url} could not be reached: {why}");
    let parsed = Url::parse(url).map_err(|why| failed(&why))?;
    let host = parsed.host_str().unwrap_or_default();
    let host = host
        .trim_start_matches('[')
        .trim_end_matches(']')
        .to_owned();
    let port = parsed.port_or_known_default().unwrap_or(80);
    let tcp = TcpStream::connect((host.as_str(), port))
        .await
        .map_err(|why| failed(&why))?;
    let _ = tcp.set_nodelay(true);
    let stream: Stream = if parsed.scheme() == "wss" {
        let config = ClientConfig::builder_with_provider(tls::provider())
            .with_safe_default_protocol_versions()
            .map_err(|why| failed(&why))?
            .with_platform_verifier()
            .map_err(|why| failed(&why))?
            .with_no_client_auth();
        let name = ServerName::try_from(host).map_err(|why| failed(&why))?;
        let connector = tokio_rustls::TlsConnector::from(Arc::new(config));
        Box::new(
            connector
                .connect(name, tcp)
                .await
                .map_err(|why| failed(&why))?,
        )
    } else {
        Box::new(tcp)
    };
    let (ws, _) = tokio_tungstenite::client_async(url, stream)
        .await
        .map_err(|why| failed(&why))?;
    Ok(ws)
}

/// The carrier a WebSocket's binary messages make: each byte read sent in a binary message,
/// each binary message received read in order; a text message, a close or an error ends it.
pub fn carried(ws: WebSocketStream<Stream>) -> Stream {
    let (ours, theirs) = tokio::io::duplex(1 << 16);
    tokio::spawn(async move {
        let (mut sink, mut messages) = ws.split();
        let (mut from, mut to) = tokio::io::split(theirs);
        // Each way apart, so that a send waiting on the peer never stops a receive.
        let receiving = async {
            while let Some(Ok(message)) = messages.next().await {
                match message {
                    Message::Binary(bytes) => {
                        if to.write_all(&bytes).await.is_err() {
                            break;
                        }
                    }
                    Message::Ping(_) | Message::Pong(_) | Message::Frame(_) => {}
                    Message::Text(_) | Message::Close(_) => break,
                }
            }
            let _ = to.shutdown().await;
        };
        let sending = async {
            let mut chunk = vec![0; CHUNK];
            while let Ok(n @ 1..) = from.read(&mut chunk).await {
                if sink
                    .send(Message::binary(chunk[..n].to_vec()))
                    .await
                    .is_err()
                {
                    break;
                }
            }
            let _ = sink.close().await;
        };
        tokio::select! {
            () = receiving => {}
            () = sending => {}
        }
    });
    Box::new(ours)
}

/// Joins the daemon `id` through the relay at `url` as a native client, and answers the
/// splice once the relay says `joined`.
pub async fn join(url: &str, id: &str) -> Result<Stream, String> {
    let mut ws = open(url).await?;
    let join = serde_json::json!({"t": "join", "id": id, "kind": "native"});
    ws.send(Message::text(join.to_string()))
        .await
        .map_err(|why| format!("the relay at {url} failed: {why}"))?;
    loop {
        let said = match ws.next().await {
            Some(Ok(Message::Text(text))) => text,
            Some(Ok(Message::Ping(_) | Message::Pong(_))) => continue,
            Some(Err(why)) => return Err(format!("the relay at {url} failed: {why}")),
            _ => return Err(format!("the relay at {url} closed.")),
        };
        let said: serde_json::Value = serde_json::from_str(&said).unwrap_or_default();
        return match said["t"].as_str() {
            Some("joined") => Ok(carried(ws)),
            Some("error") => Err(said["why"]
                .as_str()
                .unwrap_or("The relay refused.")
                .to_owned()),
            _ => Err(format!("the relay at {url} said what cannot be read.")),
        };
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipes::identity;
    use tokio::net::TcpListener;
    use tokio_tungstenite::accept_async;

    /// A relay as Section 5 of [WIRE] has it, for one daemon whose control connection is this
    /// test itself: it answers a native join of `daemon` by splicing the client to an echo of
    /// mutual TLS as that daemon, and refuses every other id.
    async fn relay(daemon: identity::Identity) -> String {
        let id = identity::fingerprint(&daemon.cert).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let at = listener.local_addr().unwrap();
        let echo = tls::tests::echoing(daemon).await;
        tokio::spawn(async move {
            while let Ok((tcp, _)) = listener.accept().await {
                let id = id.clone();
                tokio::spawn(async move {
                    let mut client = accept_async(tcp).await.unwrap();
                    let Some(Ok(Message::Text(first))) = client.next().await else {
                        return;
                    };
                    let join: serde_json::Value = serde_json::from_str(&first).unwrap();
                    if join["t"] != "join" || join["kind"] != "native" || join["id"] != id.as_str()
                    {
                        let why = format!("No daemon {} is here.", join["id"].as_str().unwrap());
                        let error = serde_json::json!({"t": "error", "why": why});
                        let _ = client.send(Message::text(error.to_string())).await;
                        return;
                    }
                    // The daemon's accepted WebSocket, which this test makes a TCP connection to
                    // the daemon's TLS: every binary message passed on unchanged.
                    let daemon = TcpStream::connect(echo).await.unwrap();
                    let joined = serde_json::json!({"t": "joined"});
                    client
                        .send(Message::text(joined.to_string()))
                        .await
                        .unwrap();
                    let (mut from, mut to) = daemon.into_split();
                    let (mut sink, mut messages) = client.split();
                    tokio::spawn(async move {
                        let mut chunk = vec![0; 4096];
                        while let Ok(n @ 1..) = from.read(&mut chunk).await {
                            let bytes = Message::binary(chunk[..n].to_vec());
                            if sink.send(bytes).await.is_err() {
                                break;
                            }
                        }
                    });
                    while let Some(Ok(message)) = messages.next().await {
                        match message {
                            Message::Binary(bytes) => to.write_all(&bytes).await.unwrap(),
                            Message::Text(_) => panic!("a text message after joined"),
                            _ => {}
                        }
                    }
                });
            }
        });
        format!("ws://{at}/")
    }

    #[tokio::test]
    async fn joins_through_a_relay_with_mutual_tls_on_the_splice() {
        let dir = tempfile::tempdir().unwrap();
        let daemon = identity::load(&dir.path().join("daemon")).unwrap();
        let me = identity::load(&dir.path().join("app")).unwrap();
        let id = identity::fingerprint(&daemon.cert).unwrap();
        let url = relay(daemon).await;
        let splice = join(&url, &id).await.unwrap();
        let mut tls = tls::connect(splice, &me, &id, "box").await.unwrap();
        // More than one message's worth, both ways.
        let sent: Vec<u8> = (0..100_000u32).map(|i| i as u8).collect();
        tls.write_all(&sent).await.unwrap();
        tls.flush().await.unwrap();
        let mine = identity::fingerprint(&me.cert).unwrap();
        let mut got = Vec::new();
        let reading = async {
            while got != sent {
                let mut buf = vec![0; 65536];
                let n = tls.read(&mut buf).await.unwrap();
                assert!(n > 0, "ended with {} bytes", got.len());
                got.extend_from_slice(&buf[..n]);
                // Each answer the echo makes starts with the client's fingerprint.
                while let Some(at) = got.windows(mine.len()).position(|w| w == mine.as_bytes()) {
                    got.drain(at..at + mine.len());
                }
            }
        };
        tokio::time::timeout(std::time::Duration::from_secs(20), reading)
            .await
            .unwrap();
    }

    #[tokio::test]
    async fn says_why_a_relay_refuses_a_join() {
        let dir = tempfile::tempdir().unwrap();
        let daemon = identity::load(&dir.path().join("daemon")).unwrap();
        let url = relay(daemon).await;
        let refused = join(&url, "nobody").await.err();
        assert_eq!(refused.as_deref(), Some("No daemon nobody is here."));
    }

    #[tokio::test]
    async fn ends_a_ws_carrier_on_a_text_message() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let at = listener.local_addr().unwrap();
        tokio::spawn(async move {
            let (tcp, _) = listener.accept().await.unwrap();
            let mut ws = accept_async(tcp).await.unwrap();
            ws.send(Message::binary(b"bytes".to_vec())).await.unwrap();
            ws.send(Message::text("no")).await.unwrap();
            ws.send(Message::binary(b"more".to_vec())).await.unwrap();
        });
        let mut carrier = carried(open(&format!("ws://{at}/")).await.unwrap());
        let mut read = Vec::new();
        carrier.read_to_end(&mut read).await.unwrap();
        assert_eq!(read, b"bytes");
    }
}
