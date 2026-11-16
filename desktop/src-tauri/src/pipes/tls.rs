//! Mutual TLS on an untrusted carrier (Section 4.4 of [WIRE]): TLS 1.3 alone, ALPN `hmz`, the
//! app's device certificate presented, and the daemon's taken for its SPKI fingerprint alone,
//! which must be the daemon id the page pins.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls::crypto::{CryptoProvider, WebPkiSupportedAlgorithms};
use rustls::{ClientConfig, DigitallySignedStruct, SignatureScheme};
use rustls_pki_types::{CertificateDer, ServerName, UnixTime};
use tokio::io::{AsyncRead, AsyncWrite};
use tokio_rustls::TlsConnector;
use tokio_rustls::client::TlsStream;

use super::identity::{self, Identity};

/// The one ALPN protocol both sides offer.
pub const ALPN: &[u8] = b"hmz";

/// What follows a daemon's name where it presents another id than the one pinned.
pub const OTHER: &str = " is not the daemon it was paired with.";

/// ring, which is all this app builds rustls with.
pub fn provider() -> Arc<CryptoProvider> {
    Arc::new(rustls::crypto::ring::default_provider())
}

/// Takes the daemon's certificate where its SPKI fingerprint is the id pinned, whatever its
/// chain, names or validity, and checks that it signed the handshake.
#[derive(Debug)]
struct Pinned {
    id: String,
    algorithms: WebPkiSupportedAlgorithms,
    /// Whether the daemon presented another id.
    other: AtomicBool,
}

impl ServerCertVerifier for Pinned {
    fn verify_server_cert(
        &self,
        end_entity: &CertificateDer<'_>,
        _intermediates: &[CertificateDer<'_>],
        _server_name: &ServerName<'_>,
        _ocsp_response: &[u8],
        _now: UnixTime,
    ) -> Result<ServerCertVerified, rustls::Error> {
        if identity::fingerprint(end_entity).as_deref() == Some(self.id.as_str()) {
            Ok(ServerCertVerified::assertion())
        } else {
            self.other.store(true, Ordering::SeqCst);
            Err(rustls::Error::General("another daemon".into()))
        }
    }

    fn verify_tls12_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        Err(rustls::Error::General("TLS 1.3 alone".into()))
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        rustls::crypto::verify_tls13_signature(message, cert, dss, &self.algorithms)
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
        self.algorithms.supported_schemes()
    }
}

/// Opens mutual TLS over `carrier` as `me`, pinning the daemon id `id`; `name` is what the
/// daemon is called where it is another.
pub async fn connect<S>(
    carrier: S,
    me: &Identity,
    id: &str,
    name: &str,
) -> Result<TlsStream<S>, String>
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let provider = provider();
    let pinned = Arc::new(Pinned {
        id: id.to_owned(),
        algorithms: provider.signature_verification_algorithms,
        other: AtomicBool::new(false),
    });
    let mut config = ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&rustls::version::TLS13])
        .map_err(|why| why.to_string())?
        .dangerous()
        .with_custom_certificate_verifier(pinned.clone())
        .with_client_auth_cert(vec![me.cert.clone()], me.key.clone_key())
        .map_err(|why| why.to_string())?;
    config.alpn_protocols = vec![ALPN.to_vec()];
    // No name is checked: the daemon is known by its key alone.
    let server = ServerName::try_from("hmz").expect("a DNS name");
    let tls = TlsConnector::from(Arc::new(config))
        .connect(server, carrier)
        .await
        .map_err(|why| {
            if pinned.other.load(Ordering::SeqCst) {
                format!("{name}{OTHER}")
            } else {
                format!("TLS with {name} failed: {why}")
            }
        })?;
    if tls.get_ref().1.alpn_protocol() != Some(ALPN) {
        return Err(format!("TLS with {name} failed: it does not speak hmz"));
    }
    Ok(tls)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use rustls::server::danger::{ClientCertVerified, ClientCertVerifier};
    use rustls::{DistinguishedName, ServerConfig};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    /// A daemon's side: admits every client certificate, as Section 4.4.5 of [WIRE] has it
    /// before pairing is asked, and keeps the client's fingerprint.
    #[derive(Debug)]
    pub struct Anyone(WebPkiSupportedAlgorithms);

    impl ClientCertVerifier for Anyone {
        fn root_hint_subjects(&self) -> &[DistinguishedName] {
            &[]
        }
        fn verify_client_cert(
            &self,
            _end_entity: &CertificateDer<'_>,
            _intermediates: &[CertificateDer<'_>],
            _now: UnixTime,
        ) -> Result<ClientCertVerified, rustls::Error> {
            Ok(ClientCertVerified::assertion())
        }
        fn verify_tls12_signature(
            &self,
            _message: &[u8],
            _cert: &CertificateDer<'_>,
            _dss: &DigitallySignedStruct,
        ) -> Result<HandshakeSignatureValid, rustls::Error> {
            Err(rustls::Error::General("TLS 1.3 alone".into()))
        }
        fn verify_tls13_signature(
            &self,
            message: &[u8],
            cert: &CertificateDer<'_>,
            dss: &DigitallySignedStruct,
        ) -> Result<HandshakeSignatureValid, rustls::Error> {
            rustls::crypto::verify_tls13_signature(message, cert, dss, &self.0)
        }
        fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
            self.0.supported_schemes()
        }
    }

    /// A daemon's TLS server, as `me`.
    pub fn daemon(me: &Identity) -> tokio_rustls::TlsAcceptor {
        let provider = provider();
        let anyone = Arc::new(Anyone(provider.signature_verification_algorithms));
        let mut config = ServerConfig::builder_with_provider(provider)
            .with_protocol_versions(&[&rustls::version::TLS13])
            .unwrap()
            .with_client_cert_verifier(anyone)
            .with_single_cert(vec![me.cert.clone()], me.key.clone_key())
            .unwrap();
        config.alpn_protocols = vec![ALPN.to_vec()];
        tokio_rustls::TlsAcceptor::from(Arc::new(config))
    }

    /// An echo daemon on loopback: answers each read with the client's fingerprint, then the
    /// bytes read.
    pub async fn echoing(me: Identity) -> std::net::SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let at = listener.local_addr().unwrap();
        let acceptor = daemon(&me);
        tokio::spawn(async move {
            while let Ok((tcp, _)) = listener.accept().await {
                let acceptor = acceptor.clone();
                tokio::spawn(async move {
                    let Ok(mut tls) = acceptor.accept(tcp).await else {
                        return;
                    };
                    let client = tls.get_ref().1.peer_certificates().unwrap()[0].clone();
                    let mut buf = [0u8; 1024];
                    while let Ok(n @ 1..) = tls.read(&mut buf).await {
                        let said = identity::fingerprint(&client).unwrap();
                        tls.write_all(said.as_bytes()).await.unwrap();
                        tls.write_all(&buf[..n]).await.unwrap();
                        tls.flush().await.unwrap();
                    }
                });
            }
        });
        at
    }

    #[tokio::test]
    async fn round_trips_over_mutual_tls_with_the_daemon_pinned() {
        let dir = tempfile::tempdir().unwrap();
        let daemon = identity::load(&dir.path().join("daemon")).unwrap();
        let me = identity::load(&dir.path().join("app")).unwrap();
        let id = identity::fingerprint(&daemon.cert).unwrap();
        let at = echoing(daemon).await;
        let tcp = tokio::net::TcpStream::connect(at).await.unwrap();
        let mut tls = connect(tcp, &me, &id, "box").await.unwrap();
        tls.write_all(b"ping").await.unwrap();
        let mine = identity::fingerprint(&me.cert).unwrap();
        let mut answer = vec![0u8; mine.len() + 4];
        tls.read_exact(&mut answer).await.unwrap();
        assert_eq!(answer, format!("{mine}ping").into_bytes());
        let (_, session) = tls.get_ref();
        assert_eq!(
            session.protocol_version(),
            Some(rustls::ProtocolVersion::TLSv1_3)
        );
    }

    #[tokio::test]
    async fn refuses_a_daemon_it_did_not_pin() {
        let dir = tempfile::tempdir().unwrap();
        let daemon = identity::load(&dir.path().join("daemon")).unwrap();
        let other = identity::load(&dir.path().join("other")).unwrap();
        let me = identity::load(&dir.path().join("app")).unwrap();
        let at = echoing(daemon).await;
        let tcp = tokio::net::TcpStream::connect(at).await.unwrap();
        let wrong = identity::fingerprint(&other.cert).unwrap();
        let refused = connect(tcp, &me, &wrong, "box").await.err();
        assert_eq!(
            refused.as_deref(),
            Some("box is not the daemon it was paired with.")
        );
    }
}
