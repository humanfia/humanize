//! The anchor link over a network: TLS 1.3, and the secret proved inside it.
//!
//! A `tcp://` or `peer://` session crosses networks nobody vouches for, so its frames go
//! inside TLS 1.3 with the application protocol `hmz-anchor`. The anchor is the server, under
//! a self-signed ECDSA P-256 certificate it makes as it starts and keeps nowhere; the cog is
//! the client, shows no certificate, and takes any server certificate whose handshake
//! signature verifies. Who is at the other end is settled one layer up, by the `HELLO`: each
//! side proves it holds the key (the token, or a meeting's ticket) by an HMAC over the SHA-256
//! of the anchor's SubjectPublicKeyInfo, the *binding*, so a proof made for one TLS session is
//! worth nothing in another. See [`Bound`].
//!
//! rustls cannot be read on one thread while it is written on another, and a [`Channel`] is,
//! so the TLS is ended on a thread of its own pumping between the TCP socket and one end of a
//! Unix socket pair; the channel runs on the other end. Closing either side ends the pump and
//! shuts the TCP socket both ways.

use std::io::{self, Read, Write};
use std::net::{Shutdown, TcpStream};
use std::os::fd::AsFd;
use std::os::unix::net::UnixStream;
use std::sync::Arc;
use std::time::Duration;

use hmac::{Hmac, Mac};
use nix::poll::{PollFd, PollFlags, PollTimeout, poll};
use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls::crypto::{CryptoProvider, verify_tls13_signature};
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer, ServerName, UnixTime};
use rustls::server::ParsedCertificate;
use rustls::{
    ClientConfig, ClientConnection, Connection, DigitallySignedStruct, ServerConfig,
    ServerConnection, SignatureScheme,
};
use sha2::{Digest, Sha256};

use crate::proto::Channel;

/// The one application protocol either side offers, and the one it closes a handshake without.
pub const ALPN: &[u8] = b"hmz-anchor";

/// What the cog's proof is an HMAC of, before the binding.
const COG: &[u8] = b"hmz-anchor cog\0";

/// What the anchor's proof is an HMAC of, before the binding and the cog's proof.
const ANCHOR: &[u8] = b"hmz-anchor anchor\0";

/// What a ticket is hashed under to name its meeting at the broker.
const TICKET: &[u8] = b"hmz-anchor ticket\0";

/// How long a handshake may take: an end that connects and says nothing is let go.
const HANDSHAKING: Duration = Duration::from_secs(30);

/// How long the last records (the `close_notify`) have to leave once either side closes.
const PARTING: Duration = Duration::from_secs(1);

/// A channel carried inside TLS: what its `HELLO` proves the other end by.
#[derive(Clone)]
pub struct Bound {
    /// SHA-256 of the DER SubjectPublicKeyInfo of the anchor's certificate.
    pub binding: [u8; 32],
    /// The token on `tcp://`, the ticket on `peer://`; `None` where nobody holds one.
    pub key: Option<Vec<u8>>,
    /// The target, as the cog names it in a refusal.
    pub whom: String,
}

impl std::fmt::Debug for Bound {
    /// Everything but the key, which no log is to hold.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Bound")
            .field("binding", &hex::encode(self.binding))
            .field("key", &self.key.as_ref().map(|_| "[redacted]"))
            .field("whom", &self.whom)
            .finish()
    }
}

impl Bound {
    /// The cog's proof that it holds the key: `HMAC-SHA256(k, "hmz-anchor cog\0" + b)`.
    pub fn cog_proof(&self) -> Option<Vec<u8>> {
        let key = self.key.as_deref()?;
        Some(
            keyed(key, &[COG, &self.binding])
                .finalize()
                .into_bytes()
                .to_vec(),
        )
    }

    /// The cog's proof as `HELLO` spelled it, raw, where it is the right one; compared in
    /// constant time.
    pub fn cog_proved(&self, said: &str) -> Option<Vec<u8>> {
        let key = self.key.as_deref()?;
        let raw = hex::decode(said).ok()?;
        keyed(key, &[COG, &self.binding])
            .verify_slice(&raw)
            .ok()
            .map(|()| raw)
    }

    /// The anchor's answer to the cog's proof `cog`:
    /// `HMAC-SHA256(k, "hmz-anchor anchor\0" + b + cog)`.
    pub fn anchor_proof(&self, cog: &[u8]) -> Option<Vec<u8>> {
        let key = self.key.as_deref()?;
        Some(
            keyed(key, &[ANCHOR, &self.binding, cog])
                .finalize()
                .into_bytes()
                .to_vec(),
        )
    }

    /// Whether `said` is the anchor's answer to `cog`, compared in constant time.
    pub fn anchor_proved(&self, cog: &[u8], said: &str) -> bool {
        let (Some(key), Ok(raw)) = (self.key.as_deref(), hex::decode(said)) else {
            return false;
        };
        keyed(key, &[ANCHOR, &self.binding, cog])
            .verify_slice(&raw)
            .is_ok()
    }
}

fn keyed(key: &[u8], parts: &[&[u8]]) -> Hmac<Sha256> {
    let mut mac = Hmac::<Sha256>::new_from_slice(key).expect("HMAC takes a key of any length");
    for part in parts {
        mac.update(part);
    }
    mac
}

/// What a half presents to the broker in place of `ticket`, which never leaves this machine:
/// `hex(SHA-256("hmz-anchor ticket\0" + ticket))`.
pub fn meeting_name(ticket: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(TICKET);
    hash.update(ticket.as_bytes());
    hex::encode(hash.finalize())
}

fn provider() -> Arc<CryptoProvider> {
    Arc::new(rustls::crypto::ring::default_provider())
}

fn failed(error: impl std::fmt::Display) -> io::Error {
    io::Error::new(
        io::ErrorKind::ConnectionRefused,
        format!("the TLS handshake failed: {error}"),
    )
}

/// The binding of a certificate: SHA-256 of its DER SubjectPublicKeyInfo.
fn binding_of(certificate: &CertificateDer<'_>) -> io::Result<[u8; 32]> {
    let parsed = ParsedCertificate::try_from(certificate).map_err(failed)?;
    Ok(Sha256::digest(parsed.subject_public_key_info().as_ref()).into())
}

/// An anchor's side of TLS: the certificate it made as it started, and the binding it gives.
pub struct Identity {
    config: Arc<ServerConfig>,
    binding: [u8; 32],
}

impl Identity {
    /// A fresh self-signed ECDSA P-256 certificate, kept in memory alone.
    pub fn fresh() -> io::Result<Identity> {
        let made = rcgen::generate_simple_self_signed(vec!["hmz-anchor".to_owned()])
            .map_err(io::Error::other)?;
        let certificate = made.cert.der().clone();
        let binding = binding_of(&certificate)?;
        let key = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(made.key_pair.serialize_der()));
        let mut config = ServerConfig::builder_with_provider(provider())
            .with_protocol_versions(&[&rustls::version::TLS13])
            .map_err(io::Error::other)?
            .with_no_client_auth()
            .with_single_cert(vec![certificate], key)
            .map_err(io::Error::other)?;
        config.alpn_protocols = vec![ALPN.to_vec()];
        // Nothing resumes: every session shows the certificate its binding is of.
        config.send_tls13_tickets = 0;
        Ok(Identity {
            config: Arc::new(config),
            binding,
        })
    }

    /// Answers TLS on an accepted or met connection, returning the channel the session runs
    /// on, bound to `key`.
    pub fn answer(
        &self,
        tcp: TcpStream,
        key: Option<Vec<u8>>,
        whom: String,
    ) -> io::Result<Channel> {
        let conn = ServerConnection::new(self.config.clone()).map_err(failed)?;
        let conn = shaken(Connection::Server(conn), &tcp)?;
        sealed(
            conn,
            tcp,
            Bound {
                binding: self.binding,
                key,
                whom,
            },
        )
    }
}

/// Opens TLS as the cog on a dialled or met connection, returning the channel the session
/// runs on, bound to `key`.
pub fn dial(tcp: TcpStream, key: Option<Vec<u8>>, whom: String) -> io::Result<Channel> {
    let provider = provider();
    let mut config = ClientConfig::builder_with_provider(provider.clone())
        .with_protocol_versions(&[&rustls::version::TLS13])
        .map_err(io::Error::other)?
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(AnyKey(provider)))
        .with_no_client_auth();
    config.alpn_protocols = vec![ALPN.to_vec()];
    config.enable_sni = false;
    config.resumption = rustls::client::Resumption::disabled();
    let name = ServerName::try_from("hmz-anchor").map_err(io::Error::other)?;
    let conn = ClientConnection::new(Arc::new(config), name).map_err(failed)?;
    let conn = shaken(Connection::Client(conn), &tcp)?;
    let shown = conn
        .peer_certificates()
        .and_then(<[_]>::first)
        .ok_or_else(|| failed("the anchor showed no certificate"))?;
    let binding = binding_of(shown)?;
    sealed(conn, tcp, Bound { binding, key, whom })
}

/// Takes whichever certificate the anchor shows, holding it only to the handshake's own
/// signature: who the anchor is, the proof in `HELLO` settles.
#[derive(Debug)]
struct AnyKey(Arc<CryptoProvider>);

impl ServerCertVerifier for AnyKey {
    fn verify_server_cert(
        &self,
        _: &CertificateDer<'_>,
        _: &[CertificateDer<'_>],
        _: &ServerName<'_>,
        _: &[u8],
        _: UnixTime,
    ) -> Result<ServerCertVerified, rustls::Error> {
        Ok(ServerCertVerified::assertion())
    }

    fn verify_tls12_signature(
        &self,
        _: &[u8],
        _: &CertificateDer<'_>,
        _: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        Err(rustls::Error::General("TLS 1.2 is refused".into()))
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        certificate: &CertificateDer<'_>,
        signed: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        verify_tls13_signature(
            message,
            certificate,
            signed,
            &self.0.signature_verification_algorithms,
        )
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
        self.0.signature_verification_algorithms.supported_schemes()
    }
}

/// Runs a handshake on a blocking socket to its end, refusing one that agreed on no `ALPN`.
fn shaken(mut conn: Connection, tcp: &TcpStream) -> io::Result<Connection> {
    let _ = tcp.set_nodelay(true);
    tcp.set_read_timeout(Some(HANDSHAKING))?;
    tcp.set_write_timeout(Some(HANDSHAKING))?;
    let done = (|| {
        while conn.is_handshaking() {
            conn.complete_io(&mut &*tcp)?;
        }
        while conn.wants_write() {
            conn.write_tls(&mut &*tcp)?;
        }
        if conn.alpn_protocol() != Some(ALPN) {
            return Err(failed("the other side does not speak hmz-anchor"));
        }
        Ok(())
    })();
    if let Err(error) = done {
        let _ = tcp.shutdown(Shutdown::Both);
        return Err(match error.kind() {
            io::ErrorKind::ConnectionRefused => error,
            _ => failed(error),
        });
    }
    tcp.set_read_timeout(None)?;
    tcp.set_write_timeout(None)?;
    Ok(conn)
}

/// Starts the pump and hands back the channel on its near end.
fn sealed(conn: Connection, tcp: TcpStream, bound: Bound) -> io::Result<Channel> {
    let (near, far) = UnixStream::pair()?;
    let channel = Channel::from_unix(near)?.with_bound(bound);
    std::thread::Builder::new()
        .name("tls-pump".into())
        .spawn(move || pump(conn, tcp, far))?;
    Ok(channel)
}

/// Carries plaintext between `near` and TLS on `tcp` until either side ends, then shuts both.
fn pump(mut conn: Connection, tcp: TcpStream, near: UnixStream) {
    if let Err(error) = pumped(&mut conn, &tcp, &near) {
        tracing::debug!("the TLS link ended: {error}");
    }
    // A `close_notify`, where there is still anyone to hear it.
    conn.send_close_notify();
    let _ = tcp.set_nonblocking(false);
    let _ = tcp.set_write_timeout(Some(PARTING));
    while conn.wants_write() && conn.write_tls(&mut &tcp).is_ok_and(|n| n > 0) {}
    let _ = tcp.shutdown(Shutdown::Both);
    let _ = near.shutdown(Shutdown::Both);
}

fn would_block(error: &io::Error) -> bool {
    matches!(
        error.kind(),
        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
    )
}

/// The pump's loop. Each side is read only once what the last read gave is passed on, so a
/// side that stops reading holds the other back rather than filling memory.
fn pumped(conn: &mut Connection, tcp: &TcpStream, near: &UnixStream) -> io::Result<()> {
    tcp.set_nonblocking(true)?;
    near.set_nonblocking(true)?;
    let mut inbound: Vec<u8> = Vec::new();
    let mut buffer = vec![0u8; 1 << 16];
    let mut far_open = true;
    loop {
        // Whatever TLS has decrypted, then as much of it as the near side takes.
        while far_open {
            match conn.reader().read(&mut buffer) {
                Ok(0) => far_open = false,
                Ok(n) => inbound.extend_from_slice(&buffer[..n]),
                Err(error) if would_block(&error) => break,
                Err(_) => far_open = false,
            }
        }
        while !inbound.is_empty() {
            match (&*near).write(&inbound) {
                Ok(n) => drop(inbound.drain(..n)),
                Err(error) if would_block(&error) => break,
                Err(error) => return Err(error),
            }
        }
        if !far_open && inbound.is_empty() {
            return Ok(());
        }

        let read_far = far_open && inbound.is_empty();
        let read_near = !conn.wants_write();
        let mut far_flags = PollFlags::empty();
        if read_far {
            far_flags |= PollFlags::POLLIN;
        }
        if conn.wants_write() {
            far_flags |= PollFlags::POLLOUT;
        }
        let mut near_flags = PollFlags::empty();
        if read_near {
            near_flags |= PollFlags::POLLIN;
        }
        if !inbound.is_empty() {
            near_flags |= PollFlags::POLLOUT;
        }
        // A side is watched only for what is wanted of it: a hung-up socket is reported
        // whatever is asked, and one watched for nothing would wake this loop for good.
        let mut fds = Vec::with_capacity(2);
        if !far_flags.is_empty() {
            fds.push(PollFd::new(tcp.as_fd(), far_flags));
        }
        if !near_flags.is_empty() {
            fds.push(PollFd::new(near.as_fd(), near_flags));
        }
        match poll(&mut fds, PollTimeout::NONE) {
            Ok(_) | Err(nix::errno::Errno::EINTR) => {}
            Err(error) => return Err(error.into()),
        }

        if read_far {
            match conn.read_tls(&mut &*tcp) {
                Ok(0) => {}
                Ok(_) => {
                    if let Err(error) = conn.process_new_packets() {
                        // The alert that says why, where there is one.
                        let _ = conn.write_tls(&mut &*tcp);
                        return Err(io::Error::new(io::ErrorKind::InvalidData, error));
                    }
                }
                Err(error) if would_block(&error) => {}
                Err(error) => return Err(error),
            }
        }
        if read_near {
            match (&*near).read(&mut buffer) {
                // The channel closed.
                Ok(0) => return Ok(()),
                Ok(n) => conn.writer().write_all(&buffer[..n])?,
                Err(error) if would_block(&error) => {}
                Err(error) => return Err(error),
            }
        }
        while conn.wants_write() {
            match conn.write_tls(&mut &*tcp) {
                Ok(_) => {}
                Err(error) if would_block(&error) => break,
                Err(error) => return Err(error),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    use crate::proto::{Frame, Op, Stream};

    fn pair(key: Option<&[u8]>) -> (Channel, Channel) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let identity = Identity::fresh().unwrap();
        let key2 = key.map(<[u8]>::to_vec);
        let served = std::thread::spawn(move || {
            let (tcp, _) = listener.accept().unwrap();
            identity.answer(tcp, key2, "cog".into()).unwrap()
        });
        let tcp = TcpStream::connect(("127.0.0.1", port)).unwrap();
        let client = dial(tcp, key.map(<[u8]>::to_vec), "anchor".into()).unwrap();
        (client, served.join().unwrap())
    }

    #[test]
    fn frames_cross_inside_tls_and_both_ends_share_the_binding() {
        let (client, server) = pair(Some(b"s3cret"));
        let (ours, theirs) = (client.bound().unwrap(), server.bound().unwrap());
        assert_eq!(ours.binding, theirs.binding);
        let cog = ours.cog_proof().unwrap();
        assert_eq!(theirs.cog_proved(&hex::encode(&cog)), Some(cog.clone()));
        assert_eq!(theirs.cog_proved("00"), None);
        let answer = theirs.anchor_proof(&cog).unwrap();
        assert!(ours.anchor_proved(&cog, &hex::encode(&answer)));
        assert!(!ours.anchor_proved(&answer, &hex::encode(&answer)));

        let big = vec![7u8; 300_000];
        client
            .send(&Frame::request(
                1,
                Op::Read,
                crate::meta! {"path" => "/w"},
                Vec::new(),
            ))
            .unwrap();
        client
            .send(&Frame::chunk(1, Stream::Data, big.clone()))
            .unwrap();
        assert_eq!(server.recv().unwrap().unwrap().id, 1);
        assert_eq!(server.recv().unwrap().unwrap().body, big);
        server.send(&Frame::end(1, Stream::Data)).unwrap();
        assert_eq!(client.recv().unwrap().unwrap().id, 1);
        // Closing one end ends the other's stream.
        client.close();
        assert!(server.recv().unwrap().is_none());
    }

    #[test]
    fn a_proof_made_with_another_key_or_binding_fails() {
        let one = Bound {
            binding: [1; 32],
            key: Some(b"k".to_vec()),
            whom: String::new(),
        };
        let other_key = Bound {
            key: Some(b"j".to_vec()),
            ..one.clone()
        };
        let other_binding = Bound {
            binding: [2; 32],
            ..one.clone()
        };
        let proof = hex::encode(one.cog_proof().unwrap());
        assert!(one.cog_proved(&proof).is_some());
        assert!(other_key.cog_proved(&proof).is_none());
        assert!(other_binding.cog_proved(&proof).is_none());
        let keyless = Bound {
            key: None,
            ..one.clone()
        };
        assert!(keyless.cog_proof().is_none());
        assert!(!keyless.anchor_proved(b"", ""));
    }

    #[test]
    fn a_plaintext_client_is_refused() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let identity = Identity::fresh().unwrap();
        let served = std::thread::spawn(move || {
            let (tcp, _) = listener.accept().unwrap();
            identity.answer(tcp, None, "cog".into()).map(|_| ())
        });
        let mut tcp = TcpStream::connect(("127.0.0.1", port)).unwrap();
        tcp.write_all(&Frame::end(1, Stream::Data).encode())
            .unwrap();
        assert!(served.join().unwrap().is_err());
    }

    #[test]
    fn proofs_and_names_are_the_ones_python_makes() {
        // The same vectors as tests/unit/coganchor/test_tls.py.
        let bound = Bound {
            binding: [1; 32],
            key: Some(b"k".to_vec()),
            whom: String::new(),
        };
        let cog = bound.cog_proof().unwrap();
        assert_eq!(
            hex::encode(&cog),
            "da5949b1478b964693b598f319d55316248da3d9f195c96853f4ba3d3cf79132"
        );
        assert_eq!(
            hex::encode(bound.anchor_proof(&cog).unwrap()),
            "4d05cf7df40a6402be008133e936b5fcd85865dbb49c38d4876ffa6099dbba32"
        );
        assert_eq!(
            meeting_name("T"),
            "a1bc7daf6bce118c3caa51afcf81bebc3ace334a2b91358f3973ec5b0c50d3df"
        );
    }
}
