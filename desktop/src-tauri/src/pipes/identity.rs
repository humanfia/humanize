//! The app's device identity (Section 4.3 of [WIRE], Section 4.3.3 of [DESKTOP]): one P-256 key
//! and its self-signed certificate in `identity/` of the data directory, made the first time a
//! pipe needs them and never made again while the key is there.

use std::fs;
use std::io::{self, Write};
use std::path::Path;

use rcgen::{CertificateParams, DistinguishedName, DnType, KeyPair, PKCS_ECDSA_P256_SHA256};
use ring::rand::{SecureRandom, SystemRandom};
use rustls_pki_types::pem::PemObject;
use rustls_pki_types::{CertificateDer, PrivateKeyDer};
use sha2::{Digest, Sha256};
use time::OffsetDateTime;

/// The device: its certificate, and its key.
pub struct Identity {
    pub cert: CertificateDer<'static>,
    pub key: PrivateKeyDer<'static>,
}

impl Clone for Identity {
    fn clone(&self) -> Self {
        Identity {
            cert: self.cert.clone(),
            key: self.key.clone_key(),
        }
    }
}

/// The identity kept in `dir`, made there first where there is none.
pub fn load(dir: &Path) -> io::Result<Identity> {
    let key_path = dir.join("key.pem");
    let cert_path = dir.join("cert.pem");
    if !key_path.exists() {
        let key = KeyPair::generate_for(&PKCS_ECDSA_P256_SHA256).map_err(io::Error::other)?;
        private_dir(dir)?;
        // Whoever writes it first wins: a key once there is never replaced.
        write_once(&key_path, key.serialize_pem().as_bytes())?;
    }
    let key = KeyPair::from_pem(&fs::read_to_string(&key_path)?).map_err(io::Error::other)?;
    // A certificate left of a key that was lost is of no use: it is made again for this one.
    let kept = fs::read(&cert_path).ok();
    let kept = kept.and_then(|pem| CertificateDer::from_pem_slice(&pem).ok());
    if kept.as_ref().and_then(spki) != Some(rcgen::PublicKeyData::subject_public_key_info(&key)) {
        if kept.is_some() {
            fs::remove_file(&cert_path)?;
        }
        write_once(&cert_path, certificate(&key)?.as_bytes())?;
    }
    let bad = |why: rustls_pki_types::pem::Error| io::Error::other(why.to_string());
    Ok(Identity {
        cert: CertificateDer::from_pem_file(&cert_path).map_err(bad)?,
        key: PrivateKeyDer::from_pem_file(&key_path).map_err(bad)?,
    })
}

/// The device certificate of a key, in PEM (Section 4.3.2 of [WIRE]).
fn certificate(key: &KeyPair) -> io::Result<String> {
    let mut params = CertificateParams::default();
    let mut name = DistinguishedName::new();
    name.push(DnType::CommonName, common_name(&host()));
    params.distinguished_name = name;
    let mut serial = [0u8; 16];
    SystemRandom::new()
        .fill(&mut serial)
        .map_err(|_| io::Error::other("no randomness"))?;
    params.serial_number = Some(serial.to_vec().into());
    params.not_before = OffsetDateTime::now_utc();
    params.not_after = time::Date::from_calendar_date(9999, time::Month::December, 31)
        .and_then(|day| day.with_hms(23, 59, 59))
        .map_err(io::Error::other)?
        .assume_utc();
    Ok(params.self_signed(key).map_err(io::Error::other)?.pem())
}

/// This machine's host name.
fn host() -> String {
    #[cfg(unix)]
    let name = {
        let mut buf = [0u8; 256];
        // SAFETY: the buffer is as long as it is said to be.
        let ok = unsafe { libc::gethostname(buf.as_mut_ptr().cast(), buf.len()) } == 0;
        let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
        ok.then(|| String::from_utf8_lossy(&buf[..end]).into_owned())
    };
    #[cfg(windows)]
    let name = std::env::var("COMPUTERNAME").ok();
    name.unwrap_or_default()
}

/// The common name of a device certificate (Section 4.3.2 of [WIRE]): `hmz` and the host name
/// up to its first `.`, cut to its first 60 characters, so that it is at most 64.
fn common_name(host: &str) -> String {
    let label = host.split('.').next().unwrap_or_default();
    format!("hmz {}", label.chars().take(60).collect::<String>())
}

/// The SPKI fingerprint of a certificate (Section 4.2.3 of [WIRE]): the SHA-256 of its
/// `SubjectPublicKeyInfo`, in lowercase base32 without padding.
pub fn fingerprint(cert: &CertificateDer<'_>) -> Option<String> {
    let digest = Sha256::digest(spki(cert)?);
    Some(
        data_encoding::BASE32_NOPAD
            .encode(&digest)
            .to_ascii_lowercase(),
    )
}

/// Makes `dir` readable by this user alone.
fn private_dir(dir: &Path) -> io::Result<()> {
    fs::create_dir_all(dir)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}

/// Writes `path` readable by this user alone, where nothing is there yet: by a link to a
/// whole file, so that it is never seen half written, nor written over.
fn write_once(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let dir = path.parent().unwrap_or(Path::new("."));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    let staged = dir.join(format!(".{}.{}", std::process::id(), random_suffix()));
    let mut file = options.open(&staged)?;
    let written = file.write_all(bytes).and_then(|()| file.sync_all());
    drop(file);
    let linked = written.and_then(|()| fs::hard_link(&staged, path));
    let _ = fs::remove_file(&staged);
    match linked {
        Err(why) if why.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        linked => linked,
    }
}

/// The DER of a certificate's `SubjectPublicKeyInfo`.
fn spki(cert: &CertificateDer<'_>) -> Option<Vec<u8>> {
    let cert = webpki::EndEntityCert::try_from(cert).ok()?;
    Some(cert.subject_public_key_info().as_ref().to_vec())
}

/// A name of its own for a file written beside the one it becomes.
pub fn random_suffix() -> String {
    let mut bytes = [0u8; 8];
    let _ = SystemRandom::new().fill(&mut bytes);
    data_encoding::HEXLOWER.encode(&bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn makes_an_identity_once_and_reuses_it() {
        let dir = tempfile::tempdir().unwrap();
        let at = dir.path().join("identity");
        let first = load(&at).unwrap();
        let again = load(&at).unwrap();
        assert_eq!(first.cert, again.cert);
        assert_eq!(first.key.secret_der(), again.key.secret_der());
        let id = fingerprint(&first.cert).unwrap();
        assert_eq!(id.len(), 52);
        assert!(
            id.bytes()
                .all(|c| c.is_ascii_lowercase() || (b'2'..=b'7').contains(&c))
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = |path: &Path| fs::metadata(path).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode(&at), 0o700);
            assert_eq!(mode(&at.join("key.pem")), 0o600);
            assert_eq!(mode(&at.join("cert.pem")), 0o600);
        }
        // Nothing but the two files.
        let mut names: Vec<_> = fs::read_dir(&at)
            .unwrap()
            .map(|entry| entry.unwrap().file_name())
            .collect();
        names.sort();
        assert_eq!(names, ["cert.pem", "key.pem"]);
    }

    #[test]
    fn makes_a_lost_certificate_again_from_the_key_it_holds() {
        let dir = tempfile::tempdir().unwrap();
        let first = load(dir.path()).unwrap();
        fs::remove_file(dir.path().join("cert.pem")).unwrap();
        let again = load(dir.path()).unwrap();
        assert_ne!(first.cert, again.cert);
        assert_eq!(fingerprint(&first.cert), fingerprint(&again.cert));
        // And one of a key that was lost is made again for the new key.
        fs::remove_file(dir.path().join("key.pem")).unwrap();
        let new = load(dir.path()).unwrap();
        assert_ne!(fingerprint(&new.cert), fingerprint(&again.cert));
        let key = KeyPair::from_pem(&fs::read_to_string(dir.path().join("key.pem")).unwrap());
        let cert = webpki::EndEntityCert::try_from(&new.cert).unwrap();
        assert_eq!(
            cert.subject_public_key_info().as_ref(),
            rcgen::PublicKeyData::subject_public_key_info(&key.unwrap())
        );
    }

    #[test]
    fn makes_the_certificate_the_protocol_states() {
        let key = KeyPair::generate_for(&PKCS_ECDSA_P256_SHA256).unwrap();
        let pem = certificate(&key).unwrap();
        let der = CertificateDer::from_pem_slice(pem.as_bytes()).unwrap();
        let cert = webpki::EndEntityCert::try_from(&der).unwrap();
        // The SPKI is the key's own.
        assert_eq!(
            cert.subject_public_key_info().as_ref(),
            rcgen::PublicKeyData::subject_public_key_info(&key)
        );
        let bytes: &[u8] = der.as_ref();
        let common = common_name(&host());
        assert!(bytes.windows(common.len()).any(|w| w == common.as_bytes()));
        // notAfter as GeneralizedTime 99991231235959Z.
        assert!(bytes.windows(15).any(|w| w == b"99991231235959Z"));
    }

    #[test]
    fn names_the_certificate_by_the_host_cut_to_60_characters() {
        assert_eq!(common_name("box.lan.example"), "hmz box");
        assert_eq!(common_name(""), "hmz ");
        let label = "a".repeat(70);
        let common = common_name(&format!("{label}.example"));
        assert_eq!(common, format!("hmz {}", "a".repeat(60)));
        assert_eq!(common.chars().count(), 64);
    }
}
