# The Humanize Protocol: Carriers, Sessions and RPC

## Abstract

This document specifies how a client reaches a daemon: the carriers that join them, the routes that
name a carrier, the device identities, mutual TLS, pairing and WebRTC that secure a carrier that is
not trusted, the relay that joins a client and a daemon that cannot reach each other, the frames
carried over a carrier, and the JSON-RPC 2.0 session whose methods [OPENRPC] lists.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [WIRE].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
- [3. Carriers and Routes](#3-carriers-and-routes)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. Route grammar](#33-route-grammar)
  - [3.4. Carriers](#34-carriers)
  - [3.5. Trust](#35-trust)
  - [3.6. Racing and reconnecting](#36-racing-and-reconnecting)
- [4. Session Security](#4-session-security)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. Device identity](#43-device-identity)
  - [4.4. Mutual TLS](#44-mutual-tls)
  - [4.5. Pairing](#45-pairing)
  - [4.6. Paired devices and revocation](#46-paired-devices-and-revocation)
  - [4.7. WebRTC](#47-webrtc)
- [5. The Relay](#5-the-relay)
  - [5.1. Scope](#51-scope)
  - [5.2. Terminology](#52-terminology)
  - [5.3. Messages](#53-messages)
  - [5.4. Registering a daemon](#54-registering-a-daemon)
  - [5.5. Joining a client](#55-joining-a-client)
  - [5.6. Limits](#56-limits)
- [6. Frames and RPC](#6-frames-and-rpc)
  - [6.1. Scope](#61-scope)
  - [6.2. Terminology](#62-terminology)
  - [6.3. Frames](#63-frames)
  - [6.4. JSON-RPC](#64-json-rpc)
  - [6.5. `session.hello` and versions](#65-sessionhello-and-versions)
  - [6.6. Errors](#66-errors)
  - [6.7. Idempotency](#67-idempotency)
  - [6.8. Subscriptions](#68-subscriptions)
  - [6.9. Files](#69-files)
  - [6.10. Limits and backpressure](#610-limits-and-backpressure)
  - [6.11. The OpenRPC document](#611-the-openrpc-document)
- [7. Security Considerations](#7-security-considerations)
- [8. References](#8-references)
  - [8.1. Normative References](#81-normative-references)

## 1. Introduction

Every frontend of hmz -- the terminal interface, the command line, the web page, the desktop
application and a program using the software development kit -- is a client of a daemon, and no
frontend holds an epic in its own process. A client reaches a daemon through four layers:

- L0, a carrier: any byte pipe between the client and the daemon (Section 3).
- L1, security, on a carrier that is not trusted alone: mutual TLS between pinned device
  certificates, or, from a browser, WebRTC with pinned DTLS fingerprints (Section 4).
- L2, frames: a length followed by one JSON object (Section 6.3).
- L3, a JSON-RPC 2.0 session whose methods [OPENRPC] lists and [DAEMON] specifies (Section 6.4).

This document is organised as follows:

- Section 3: Carriers and Routes.
- Section 4: Session Security.
- Section 5: The Relay.
- Section 6: Frames and RPC.

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

**2.1** A **client** is a process that speaks to a daemon over a session: a frontend, `hmz daemon
connect --stdio` relaying for one, or the bridge of `hmz web` (Section 4 of [WEB]).

**2.2** A **session** is one carrier between one client and one daemon, from the moment it is
opened until either side closes it, together with the state the daemon keeps of it.

**2.3** **Base32** is the encoding of Section 6 of [RFC4648], written in lowercase letters and
without padding.

**2.4** **Base64url** is the encoding of Section 5 of [RFC4648] without padding, and **base64** the
encoding of Section 4 of [RFC4648] with padding.

## 3. Carriers and Routes

### 3.1. Scope

Section 3 specifies the carriers a client reaches a daemon over, the text that names one, which
carriers are trusted, and how a client chooses among several routes to one daemon and reconnects.

Out of scope:

- What secures a carrier that is not trusted: Section 4.
- The relay a `relay:` or `webrtc:` route goes through: Section 5.
- Where a client keeps the routes of each daemon: Section 3.4.6 of [FILES] and Section 3.13 of
  [WEB].
- Installing hmz on the machine of a `stdio:ssh` route: Section 3.8.3 of [DAEMON].

### 3.2. Terminology

**3.2.1** A **carrier** is an ordered, reliable stream of bytes in each direction between a client
and a daemon, which either side MAY close.

**3.2.2** A **route** is the text, of the grammar of Section 3.3, that names one carrier to one
daemon.

**3.2.3** A carrier is **trusted** where reaching its daemon end already proves that the client acts
as the daemon's user, and **untrusted** otherwise (Section 3.5).

**3.2.4** A **listener** is a carrier end a daemon offers to clients beside its socket, named by a
listener spec (Section 3.9.2 of [DAEMON]).

**3.2.5** The **hmz a login shell finds** on a machine is the `hmz` found on the `PATH` that
`"$SHELL" -lc` of the user there gives, `/bin/sh` standing for `$SHELL` where it is not set.

### 3.3. Route grammar

**3.3.1** A route MUST match `route` of the following grammar, in which `host`, `port`, `userinfo`,
`path-abempty`, `unreserved` and `pct-encoded` are those of [RFC3986]:

```abnf
route          = unix-route / local-route / ssh-route / wsl-route / tcp-route / ws-route
               / easytier-route / relay-route / webrtc-route
unix-route     = "unix:" [ abs-path ]
local-route    = "stdio:local"
ssh-route      = "stdio:ssh://" [ userinfo "@" ] host [ ":" port ] [ "?" ssh-param
                 *( "&" ssh-param ) ]
ssh-param      = ( "identity=" / "jump=" / "option=" ) 1*( unreserved / pct-encoded / "=" )
wsl-route      = "stdio:wsl" [ ":" distro ]
distro         = 1*( unreserved / pct-encoded )
tcp-route      = "tcp://" host ":" port
ws-route       = ws-url
ws-url         = ( "ws://" / "wss://" ) host [ ":" port ] path-abempty
easytier-route = "easytier:" name
relay-route    = "relay:" ws-url
webrtc-route   = "webrtc:" ws-url
name           = ( ALPHA / DIGIT ) *( ALPHA / DIGIT / "." / "_" / "-" )
abs-path       = "/" *( unreserved / pct-encoded / "/" )
```

**3.3.2** A client MUST refuse a route that does not match the grammar with `<route> is not a
route.`, and MUST refuse a route whose carrier it does not offer with `<route> cannot be reached
from here.`

**3.3.3** The parameters of a `stdio:ssh` route MUST be read after percent-decoding: `identity` the
identity file, `jump` the proxy jump, and each `option` one ssh option `<Keyword>=<value>`, in the
order given; a host that is the alias of a `Host` of the ssh configuration MUST be resolved by `ssh`
itself each time the route is opened.

**3.3.4** `port` MUST be a decimal number from 1 to 65535 and `host` MUST NOT be empty, in every
route that holds them; a route that breaks either MUST be refused as one the grammar does not
match.

**3.3.5** A `stdio:ssh` route whose destination -- `<user>@<host>` after percent-decoding, or
`<host>` where it names no user -- starts with `-`, or holds a space, a tab, a carriage return, a
line feed or a NUL, MUST be refused with `<route> cannot be reached from here.`, so that `ssh` reads
no destination as an option or as more than one.

### 3.4. Carriers

**3.4.1** `unix:` MUST be a connection to the socket of the daemon of this machine (Section 4.2.3 of
[DAEMON]), started where none runs (Section 3.4 of [DAEMON]); `unix:<path>` MUST be a connection to
the Unix stream socket at `<path>`, started nowhere.

**3.4.2** `stdio:local` MUST be the standard input and output of `hmz daemon connect --stdio`
(Section 13 of [CLI]), started on this machine with the hmz a login shell finds (Section 3.2.5),
`$HOME/.local/bin` added to that `PATH` where it lacks it.

**3.4.3** `stdio:ssh://…` MUST be the standard input and output of `hmz daemon connect --stdio` run
on the host the route names through `ssh` with the user, port, identity file, proxy jump and options
it names, after the hmz there is found and, where needed, installed as Section 3.8.3 of [DAEMON]
states; `ssh` MUST be run in batch mode, so that it asks for no password and accepts no unknown host
key. The command MUST be run by the shell `ssh` starts there, which MAY run it through a login
shell, with `$HOME/.local/bin` put in front of `PATH`.

**3.4.4** `stdio:wsl[:<distro>]` MUST be the standard input and output of `wsl.exe [-d <distro>]
--exec`, running `"$SHELL" -lc` there as Section 3.2.5 states, which runs `hmz daemon connect
--stdio` with `$HOME/.local/bin` put in front of `PATH`; without `<distro>` it MUST be the default
distribution.

**3.4.5** `tcp://<host>:<port>` MUST be a TCP connection to that host and port.

**3.4.6** `ws://…` and `wss://…` MUST be a WebSocket [RFC6455] opened on that URL, whose binary
messages carry consecutive bytes of the carrier; a text message on it MUST close it.

**3.4.7** `easytier:<name>` MUST be a TCP connection, through a port of this machine's loopback, to
the daemon port of the EasyTier network the EasyTier entry `<name>` of the dialing side names,
joined as Section 3.8.5 of [DAEMON] states.

**3.4.8** `relay:<url>` MUST be the byte splice of a native join through the relay at `<url>`
(Section 5.5), and `webrtc:<url>` the data channel of a WebRTC connection signalled through the
relay at `<url>` (Section 4.7).

**3.4.9** A client that opens a carrier MUST give up on it unless, within 30 seconds of starting it,
the carrier has opened, its security of Section 4, if any, is established and `session.hello`
(Section 6.5) over it is answered, and MUST then report `<route> did not open within 30 seconds.`;
a `stdio:` carrier opens as soon as its process starts and says nothing but the line of Section
3.4.11 until it is spoken to, so that its 30 seconds are those of its handshake. The time the user
is asked whether to install hmz over a `stdio:ssh` carrier (Section 3.8.3.7 of [DAEMON]) and the
time hmz is installed over it MUST NOT count, and the 30 seconds MUST start afresh once the user has
answered and once it is installed.

**3.4.10** A carrier MUST NOT be half-closed: a side that stops reading or writing it MUST close it
both ways, and whatever splices a carrier to another or to standard streams -- `hmz daemon connect
--stdio` (Section 13.2.3 of [CLI]), the relay (Section 5.5.3), `/rpc` and `/dial` (Section 4.7 of
[WEB] and Section 4.8 of [WEB]) and the pipes of the desktop application (Section 3.12 of
[DESKTOP]) -- MUST close both once either direction ends.

**3.4.11** `hmz daemon connect --stdio` MUST write `hmz-stdio/1` and a line feed to its standard
output before any byte of the daemon's, and a `stdio:` carrier MUST be what its client reads after
the first such line, every byte up to and including that line being discarded: what a shell that
`ssh` or WSL starts prints before the command runs. A client MUST give up on a `stdio:` carrier
whose first 65 536 bytes hold no such line.

### 3.5. Trust

**3.5.1** `unix:`, `stdio:local`, `stdio:ssh` and `stdio:wsl` carriers MUST be trusted: the
operating system, `ssh` or WSL has already admitted the client as the daemon's user.

**3.5.2** `tcp`, `ws`, `wss`, `easytier`, `relay` and `webrtc` carriers MUST be untrusted.

**3.5.3** Frames (Section 6.3) MUST be carried directly on a trusted carrier, and MUST be carried on
an untrusted carrier only inside the mutual TLS of Section 4.4, or, for `webrtc`, inside the data
channel of Section 4.7.

**3.5.4** A session over a trusted carrier MUST be paired from its start, as the device `local`.

**3.5.5** `wss` and the TLS a user puts in front of a relay MUST NOT make a carrier trusted.

**3.5.6** A client MUST refuse to open an untrusted route of a daemon whose id it does not pin,
before it opens the carrier, with `<route> needs the id of the daemon it reaches.`

### 3.6. Racing and reconnecting

**3.6.1** A client that knows several routes of one daemon MUST try them in the order kept, starting
each 250 milliseconds after the one before it started, or at once where every route started before
it has failed.

**3.6.2** The client MUST keep the first session whose `session.hello` (Section 6.5) is answered
with a result whose `daemon_id` is the one the client pins, and MUST close every other attempt.

**3.6.3** A client MUST read a daemon as unreachable once every route has failed, with the failure
of the last route to fail, and a daemon that has no route with `There is no route to try.`

**3.6.4** A session that drops or fails MUST be tried again after 1 second, the wait doubling after
each further failure up to at most 60 seconds, and starting again at 1 second once a session is up,
but where Section 3.8.3.9 of [DAEMON] states otherwise.

**3.6.5** A client that reconnects MUST attach again to every subscription it held, with `since`
(Section 6.8.4).

## 4. Session Security

### 4.1. Scope

Section 4 specifies the identity of a device, the mutual TLS that secures an untrusted native
carrier, how a client is paired with a daemon, how a pairing is revoked, and how a browser secures
a WebRTC carrier.

Out of scope:

- The files the identity and the paired devices are kept in: Section 4.14 of [FILES].
- The commands that pair and revoke: Section 17 of [CLI].
- The methods `pair.*` and `devices.*`: Section 4.14 of [DAEMON].

### 4.2. Terminology

**4.2.1** A **device** is one machine's installation of hmz, one desktop application, or one
browser profile, as a party to sessions.

**4.2.2** A **device certificate** is the self-signed X.509 certificate [RFC5280] of a native device
(Section 4.3).

**4.2.3** The **SPKI fingerprint** of a certificate is the SHA-256 of the DER encoding of its
`SubjectPublicKeyInfo`, written in base32 (52 characters).

**4.2.4** The **daemon id** of a daemon is the SPKI fingerprint of the device certificate of its
machine.

**4.2.5** The **device fingerprint** of a client is the SPKI fingerprint of its device certificate,
or, for a browser over WebRTC, `dtls:` followed by the SHA-256 of the DER encoding of its DTLS
certificate in base32.

**4.2.6** A **pairing code** is the text of Section 4.5.2 that admits one device to a daemon once.

**4.2.7** A session is **paired** where its client's device fingerprint is among the daemon's paired
devices, or its carrier is trusted, and **unpaired** otherwise.

### 4.3. Device identity

**4.3.1** Each native device MUST hold one key pair on the curve P-256 [FIPS186-5] and one device
certificate for it, made the first time hmz needs either and kept as Section 4.14 of [FILES] states.

**4.3.2** A device certificate MUST be X.509 version 3, self-signed with ECDSA and SHA-256, with a
serial number of 16 random bytes, the subject and issuer common name `hmz <host>` (`<host>` this
machine's host name up to its first `.`, cut to its first 60 characters, so that the common name
is at most the 64 characters X.509 allows), a `notBefore` of the moment it was made and a `notAfter`
of `99991231235959Z`.

**4.3.3** The daemon of a machine and every client on that machine MUST use that machine's one
device certificate; its daemon id is therefore also that machine's device fingerprint as a client.

**4.3.4** A device MUST NOT reveal its private key, MUST NOT put it on a command line, and MUST NOT
make a new key pair while it holds one.

**4.3.5** The desktop application MUST hold a device certificate of its own, as Section 4.3 of
[DESKTOP] states, and a browser MUST hold a persistent DTLS certificate of its own (Section 4.7.2).

### 4.4. Mutual TLS

**4.4.1** On an untrusted native carrier the client MUST open TLS 1.3 [RFC8446] as the TLS client
and the daemon MUST answer as the TLS server; neither MUST accept another version of TLS.

**4.4.2** Each side MUST present its device certificate, and the daemon MUST request the client's.

**4.4.3** Each side MUST NOT refuse a certificate for its chain, its names or its validity period,
and MUST instead check the other's certificate as Section 4.4.4 and Section 4.4.5 state.

**4.4.4** The client MUST close the carrier, sending no frame, where the SPKI fingerprint of the
daemon's certificate is not the daemon id it pins, and MUST report `<name> is not the daemon it was
paired with.`, `<name>` being the client's name for the daemon (Section 3.8.1 of [DAEMON]), or the
route where whatever opens TLS is given no name, as a pipe of [DESKTOP] is not.

**4.4.5** The daemon MUST admit every client certificate whose self-signature verifies under the
public key that certificate holds, and MUST read the session as paired or unpaired by the client's
SPKI fingerprint.

**4.4.6** Both sides MUST offer the ALPN [RFC7301] protocol `hmz`, and MUST close a handshake that
agrees on another.

**4.4.7** The client MUST pin the daemon id given by a pairing code (Section 4.5), or, where the
daemon was first reached over a trusted carrier, the `daemon_id` that carrier's `session.hello`
answered, and MUST NOT pin one learned over an untrusted carrier alone.

### 4.5. Pairing

**4.5.1** A daemon MUST make a pairing code when `pair.create` is called on a paired session
(Section 4.14.2 of [DAEMON]), which `hmz devices pair` does over the socket (Section 17 of [CLI]).

**4.5.2** A pairing code MUST be the text `hmz-pair:` followed by the base64url of the UTF-8 JSON
object `{"v": 1, "id": <daemon id>, "routes": [<route>, ...], "token": <token>, "expires": <Unix
seconds>}`, with exactly those keys.

**4.5.3** `token` MUST be 32 random bytes in base64url, made afresh for each code.

**4.5.4** `expires` MUST be the moment the code stops admitting, 600 seconds after it was made
unless `pair.create` asked for another lifetime of 60 to 86 400 seconds.

**4.5.5** `routes` MUST be the routes `pair.create` was given, else those of the daemon's listeners
(Section 3.9.3 of [DAEMON]).

**4.5.6** A daemon MUST keep the tokens of the codes it made in its memory alone, at most 16 of
them, dropping the oldest, and MUST forget each once it is claimed or expired.

**4.5.7** A client given a pairing code MUST reach the daemon over the code's routes, pinning the
code's `id`, and MUST call `pair.claim` with the code's `token` and the name of its device; it MUST
then keep the daemon's id and routes as Section 3.4.6 of [FILES] or Section 3.13 of [WEB] states.

**4.5.8** `pair.claim` MUST admit the session's device fingerprint where the token is one the daemon
holds and has not expired, MUST then forget the token, and MUST make the session paired at once; on
a session paired already it MUST admit nothing more (Section 4.14.2.3 of [DAEMON]).

**4.5.9** A token MUST be compared in constant time, and a token not held, claimed or expired MUST
be refused 403, `That pairing code is not valid: ask for a new one.`

**4.5.10** An unpaired session MUST be refused every method but `session.hello`, `pair.claim` and
`rpc.discover`, with 401, `This device is not paired: claim a pairing code first.`

### 4.6. Paired devices and revocation

**4.6.1** A daemon MUST keep each paired device as its name, its device fingerprint, when it was
added and when a session of it was last seen, as Section 4.14 of [FILES] states.

**4.6.2** The name of a paired device MUST be the name `pair.claim` gave, made unique by `#2`, `#3`
and on; a device MUST be renamed by revoking it and pairing it again.

**4.6.3** Revoking a device (`devices.revoke`, Section 4.14.3 of [DAEMON]) MUST remove its entry,
MUST answer the call, and MUST then close, at once, every session of the daemon whose device
fingerprint is that device's, the one that called included.

**4.6.4** `local` MUST NOT be revocable: revoking it MUST be refused with `local cannot be
revoked.`

### 4.7. WebRTC

**4.7.1** A browser MUST reach a daemon's `webrtc:<url>` route by WebRTC [RFC8831] [RFC8832], as the
offerer, signalled through the relay at `<url>` (Section 5.5), with the daemon as the answerer.

**4.7.2** A browser MUST make its DTLS certificate with `RTCPeerConnection.generateCertificate` on
ECDSA P-256 with the longest lifetime the browser allows, asked as 100 years (`expires` 3 153 600
000 000 milliseconds) and cut to its own longest by the browser, MUST keep it in its IndexedDB, and
MUST use it for every connection until it expires; a browser whose certificate expired or was lost
is a new device and MUST be paired again.

**4.7.3** The offer MUST open exactly one data channel, labelled `hmz`, ordered and reliable, whose
binary messages carry consecutive bytes of the carrier, each at most 16 384 bytes; a text message on
it MUST close it.

**4.7.4** Each signal (Section 5.5.5) MUST be `{"type": "offer", "sdp"}` from the browser, `{"type":
"answer", "sdp", "cert", "sig"}` from the daemon, or `{"type": "candidate", "candidate", "sdpMid",
"sdpMLineIndex"}` from either; a side MAY gather every candidate into its description and send no
`candidate`.

**4.7.5** In `answer`, `cert` MUST be the daemon's device certificate in base64 of its DER encoding,
and `sig` the base64url of the ECDSA P-256 SHA-256 signature, as the 64 bytes of `r` and `s`, by the
daemon's device key over the UTF-8 text `hmz-webrtc/1`, a line feed, the `sha-256` fingerprint of
the offer's SDP as written there, a line feed, and the `sha-256` fingerprint of the answer's SDP as
written there (Section 4.7.12).

**4.7.6** The browser MUST close the connection, before it carries any frame, where the SPKI
fingerprint of `cert` is not the daemon id it pins, where `sig` does not verify under the key of
`cert`, or where the offer fingerprint signed is not that of its own offer.

**4.7.7** The daemon MUST read the device fingerprint of the session as `dtls:` followed by the
base32 of the bytes of the offer's `sha-256` fingerprint, which DTLS has held the browser to.

**4.7.8** STUN and TURN servers MUST be those of the setting `ice_servers` (Section 3.4.9 of
[FILES]) on the daemon's side, and those the page keeps on the browser's side (Section 3.13 of
[WEB]); hmz MUST NOT serve STUN or TURN of its own.

**4.7.9** A daemon MUST answer WebRTC only where its `listen` names a `webrtc:` listener and the
optional dependency `webrtc` is installed, and MUST say `webrtc` among its capabilities (Section
6.5.4) then alone.

**4.7.10** A daemon that will not answer a WebRTC join -- one that cannot answer WebRTC (Section
4.7.9), an offer refused by Section 4.7.13, or a data channel other than that of Section 4.7.3 --
MUST send `refuse` with its `why` for that join's `conn` on its control connection (Section 5.5.3),
which the relay passes to the browser (Section 5.5.8), so that the browser need not wait out
Section 3.4.9.

**4.7.11** WebRTC MUST be offered by a browser alone: a native WebRTC stack makes a new DTLS
certificate for each connection, so that its device fingerprint would change each time and could
never be paired. A native client MUST reach a daemon through a relay by its `relay:` route, and MUST
refuse a `webrtc:` route as Section 3.3.2 states.

**4.7.12** The `sha-256` fingerprint of a description MUST be the value that follows `sha-256` and
its spaces on an `a=fingerprint:` line of it, the algorithm's name read in any case: 32 bytes in
hexadecimal, a colon between each, signed with the case of its letters kept as written.

**4.7.13** A description MUST carry exactly one distinct `sha-256` value, which it MAY repeat in
each media section and beside fingerprints of other algorithms; a description that carries none or
two MUST be refused with `A description must say exactly one sha-256 fingerprint.`, and one whose
value is not of the form of Section 4.7.12 with `<value> is not a sha-256 fingerprint.`

## 5. The Relay

### 5.1. Scope

Section 5 specifies `hmz relay serve` as its peers see it: the WebSocket messages a daemon registers
with, those a client joins with, the byte splice of a native join and the signals of a WebRTC join.

Out of scope:

- The command line of `hmz relay serve`: Section 14 of [CLI].
- The TLS a user puts in front of a relay, which the relay neither needs nor knows.

### 5.2. Terminology

**5.2.1** The **relay** is one process of `hmz relay serve`.

**5.2.2** A **room** is what the relay keeps for one daemon id while a daemon is registered under
it.

**5.2.3** A **control connection** is the WebSocket a daemon registers over; a **join** is one
client's request to reach a registered daemon, named by a **conn**, a text the relay makes of at
least 16 random bytes in base64url.

### 5.3. Messages

**5.3.1** Every connection to the relay MUST be a WebSocket [RFC6455] opened on any path of the
relay's URL.

**5.3.2** A control message MUST be a text message holding one JSON object whose `t` names its kind;
a binary message MUST carry bytes of a splice alone (Section 5.5.3).

**5.3.3** The relay MUST answer a message it cannot read, or one of a kind it does not expect there,
with `{"t": "error", "why": "<sentence>"}` and close the connection.

**5.3.4** The sentence MUST be `That message cannot be read.` for a text message that is not a JSON
object whose `t` is a text, and for a `signal` whose `data` is not an object; `A binary message is
not expected here.` for a binary message where a control message is expected; and `A <t> is not
expected here.` for a control message whose kind `<t>` is not expected there.

**5.3.5** The relay MUST close, with `error` `Nothing was said in time.`, a connection whose first
message has not come within 10 seconds of its opening, and a control connection whose `prove` has
not come within 10 seconds of its `challenge`.

### 5.4. Registering a daemon

**5.4.1** A daemon with a `relay:` or `webrtc:` listener MUST keep one control connection to that
relay, opened again as Section 3.6.4 states where it drops, and MUST send `{"t": "register", "id":
<daemon id>}` first.

**5.4.2** The relay MUST answer `{"t": "challenge", "nonce": <32 random bytes in base64url>}`, and
the daemon `{"t": "prove", "cert": <its device certificate, base64 of DER>, "sig": <base64url of the
64-byte ECDSA P-256 SHA-256 signature by its device key over the UTF-8 text `hmz-relay/1`, a line
feed and the nonce>}`, the nonce signed as the base64url text it was sent as, not as the bytes it
decodes to.

**5.4.3** The relay MUST answer `{"t": "registered"}` where the SPKI fingerprint of `cert` is `id`
and `sig` verifies, and MUST refuse with `error` `That daemon id is not proven.` otherwise.

**5.4.4** A daemon registered under an id already registered MUST take the room, and the relay MUST
close the earlier control connection.

**5.4.5** The relay MUST drop a room when its control connection closes, and MUST then close every
join of it that is not yet spliced.

### 5.5. Joining a client

**5.5.1** A client MUST send `{"t": "join", "id": <daemon id>, "kind": "native" | "webrtc"}` first;
the relay MUST refuse with `error` `A join of kind <kind> cannot be made.` where `kind` is neither,
and otherwise `No daemon <id> is here.` where no room has that id.

**5.5.2** The relay MUST send the daemon `{"t": "join", "conn": <conn>, "kind": <kind>}` on its
control connection.

**5.5.3** For a native join, the daemon MUST open a new WebSocket to the relay and send `{"t":
"accept", "conn": <conn>}` first, or MUST send `{"t": "refuse", "conn": <conn>, "why"}` on its
control connection; the relay MUST then send the client `{"t": "joined"}`, or `error` with `why`,
and from `joined` on MUST carry every binary message of either WebSocket to the other, unchanged and
in order, closing each when the other closes.

**5.5.4** A native join not accepted within 10 seconds of the client's `join` MUST be refused with
`error` `The daemon did not answer.`

**5.5.5** For a WebRTC join, the relay MUST send the client `{"t": "joined"}` at once, and then MUST
pass each `{"t": "signal", "data": <object>}` the client sends to the daemon as `{"t": "signal",
"conn": <conn>, "data": <object>}`, and each such message the daemon sends to that client as `{"t":
"signal", "data": <object>}`; the client MAY close its WebSocket once its data channel is open.

**5.5.6** The relay MUST NOT read, keep or log the bytes of a splice, and MUST NOT keep anything on
disk.

**5.5.7** The relay MUST refuse with `error` `A native join sends nothing before it is joined.` a
native client that sends anything before `joined`; with `No join <conn> is waiting.` an `accept`
whose `conn` names no native join still waiting for its answer; and with `A splice carries binary
messages alone.` a text message on either WebSocket of a splice, which then closes the splice.

**5.5.8** For a WebRTC join, the relay MUST answer a `refuse` of the daemon by sending the client
`error` with its `why` and closing the client's connection.

**5.5.9** The relay MUST drop, unanswered, a `signal` or a `refuse` of a daemon whose `conn` names
no join of its room still open, a `signal` whose `conn` names a native join, and a `refuse` of a
native join already answered.

### 5.6. Limits

**5.6.1** The relay MUST close a connection that sends a text message over 65 536 bytes or a binary
message over 1 048 576 bytes.

**5.6.2** The relay MUST ping every connection every 30 seconds, and MUST close one that has not
answered a ping with a pong within 60 seconds of it.

**5.6.3** The relay MUST close a client connection that sends anything but `join` and, for a WebRTC
join, `signal`, before `joined`, and a binary message before `joined`.

## 6. Frames and RPC

### 6.1. Scope

Section 6 specifies the frames carried over a session, the JSON-RPC 2.0 messages they carry, the
handshake and its version rule, the errors, idempotent writes, subscriptions, file transfer in
chunks, the limits a session is held to, and the OpenRPC document that lists every method.

Out of scope:

- What each method does: Section 4 of [DAEMON].
- The messages an epic subscription carries: Section 4.9 of [DAEMON].

### 6.2. Terminology

**6.2.1** A **frame** is one unit carried over a session, as Section 6.3 defines it.

**6.2.2** A **call** is a JSON-RPC request that carries `id`; a **notification** is one without.

**6.2.3** A **write** is a method whose parameters in [OPENRPC] include `idem`.

**6.2.4** A **subscription** is a stream of notifications the daemon sends a session under a `sub`
named by the call that opened it.

**6.2.5** A **handle** is a text naming one file a session reads or writes in chunks.

### 6.3. Frames

**6.3.1** Every byte a session carries after its L1, if any, and on a `stdio:` carrier after the
line of Section 3.4.11, MUST belong to a frame: the length of its payload as an unsigned 32-bit
big-endian integer, then the payload, one JSON object in UTF-8.

**6.3.2** A reader MUST accept a payload of 1 to 33 554 432 bytes, and MUST close the session on a
length of 0 or above it.

**6.3.3** A writer MUST encode JSON without escaping non-ASCII characters and MUST encode every
value that is not JSON-native as its text.

**6.3.4** A reader MUST hand out each whole frame exactly once, in the order received.

### 6.4. JSON-RPC

**6.4.1** Every frame MUST carry one JSON-RPC 2.0 request, notification or response [JSONRPC]; a
batch MUST be answered with the error -32600, `Send one request a frame.`, and `id` `null`. A frame
that is JSON but neither a batch nor a request, notification or response of JSON-RPC 2.0 MUST be
answered with -32600, `That is not a JSON-RPC 2.0 request.`, its `id` that of the call where it is a
call whose `id` is a text or an integer, and `null` otherwise; a notification whose `method` is not
a text or whose `params` is not an object, and a response that answers no call of the session still
unanswered, MUST be dropped.

**6.4.2** A client MUST send calls and the notification `session.cancel`; the daemon MUST send
responses and notifications, and MUST NOT send a call; a call a client is sent MUST be answered
with -32601.

**6.4.3** Every call MUST carry `id`, a text or an integer not in use by another call of the session
still unanswered, and `params` as an object, or none for no parameters; a call whose `id` is that of
such a call MUST be refused with -32600, `That id is in use by another call.`, and `id` `null`, so
that the refusal answers neither call.

**6.4.4** The daemon MUST answer every call exactly once on the session it came in on, and MAY
answer calls in another order than they were made, but for Section 6.4.5.

**6.4.5** The daemon MUST carry out the calls of one session that name one subscription in the order
sent, except `epic.aside` and the calls to an environment (Section 4.24 of [DAEMON]), which MUST be
carried out apart so that no other call waits on them.

**6.4.6** A call of one session MUST NOT delay the calls or notifications of another.

**6.4.7** `session.cancel` with `id` MUST ask the daemon to give up a call of that session; the
daemon MAY carry it on, and MUST answer a call it gives up with the error -32800.

**6.4.8** A client MUST ignore a notification whose method it does not know, and a field of a result
or of a notification it does not know.

### 6.5. `session.hello` and versions

**6.5.1** The protocol version this document defines MUST be `3.0.0`, a version of [SEMVER].

**6.5.2** The first call of a session MUST be `session.hello`; any other first call MUST be refused
with -32600, `A client says session.hello first.`, and `session.hello` called again with -32600,
`This session has already said hello.`

**6.5.3** `session.hello` MUST take `protocol`, the client's protocol version, and `client`, `{name,
kind}`: `name` the user's name for the client (Section 4.7.1.5 of [DAEMON]) and `kind` one of `tui`,
`web`, `desktop`, `cli`, `sdk`, `bridge` and `ai-chan`, the last only as Section 4.22.6.2 of
[DAEMON] permits. A `protocol` that is not a version of [SEMVER] MUST be
refused with -32602, `session.hello takes protocol as a version.`

**6.5.4** `session.hello` MUST be answered with `daemon_id`, `version` (the daemon's hmz version),
`protocol` (the daemon's protocol version), `capabilities` (a list of text naming optional features
the daemon offers; this version defines `webrtc`), `machine` (the daemon's host name up to its first
`.`), `wsl` (the WSL distribution it runs in, as `WSL_DISTRO_NAME` names it, or `null`), `newer` (a
newer release of hmz, as Section 13 of [CORE] defines it, or `""`), `paired` (whether the session is
paired) and `device` (the name of the client's paired device, `local` over a trusted carrier, `""`
where unpaired).

**6.5.5** The daemon MUST accept a client whose protocol has its own major version and a minor
version no greater than its own, and MUST refuse every other with 426, its `data` holding the
daemon's `protocol`.

**6.5.6** The message of that refusal MUST be ``held for frontends by a newer Humanize; `hmz` of it
reads it`` where the client's protocol is older than the daemon's, and `the runs on this machine are
held by an older Humanize (pid <pid>); stop it with that version` where it is newer.

**6.5.7** A client refused with 426 MUST NOT call anything more on that session, MUST NOT start a
daemon beside the one that refused, and MUST report the refusal's message.

### 6.6. Errors

**6.6.1** An error MUST carry `code`, `message` -- one sentence saying why, in the words this
protocol gives -- and, where a method states further fields, `data`, an object holding them.

**6.6.2** The codes MUST be those of the following table.

| Code | Meaning |
| --- | --- |
| -32700 | The frame does not hold JSON: `Send JSON.` |
| -32600 | Not a JSON-RPC 2.0 request, a batch, or a call before `session.hello` |
| -32601 | No such method: `There is no method <method>.` |
| -32602 | Parameters not as [OPENRPC] states (Section 6.6.3) |
| -32603 | A failure the method does not anticipate: `Something went wrong here: <why>` |
| -32800 | The call was given up: `The call was cancelled.` |
| 400 | A value the method refuses |
| 401 | The session is unpaired (Section 4.5.10) |
| 403 | Refused to this device, a pairing code not valid included, or out of a session's reach (Section 4.21 of [DAEMON]) |
| 404 | What the call names does not exist |
| 409 | Refused in the state things are in, a host's refusal included |
| 410 | No such subscription: `There is no subscription <sub>.` |
| 413 | More than a call or an answer here may carry |
| 426 | Another protocol version (Section 6.5.5) |
| 502 | A program or service the daemon asked did not answer |
| 503 | What the call needs cannot be reached now |

**6.6.3** Parameters MUST be refused -32602 with `<method> takes no <names>.` for a parameter the
method does not take, `<method> takes <name> as <type>.` for one of another type, and `<method>
needs <name>.` for a required one absent.

**6.6.4** A host's refusal (Section 4.7.2 of [DAEMON]) MUST be answered 409 with the host's `why` as
the message.

**6.6.5** An unanticipated failure MUST be written with its traceback to `daemon.log` (Section 7.6.5
of [FILES]), not into the answer.

### 6.7. Idempotency

**6.7.1** A write MAY carry `idem`, a text of 1 to 64 characters the client chooses afresh for each
write it means once.

**6.7.2** The daemon MUST keep, per device fingerprint, the answer of each write that carried
`idem`, for 600 seconds, and at most the latest 1 024 of them.

**6.7.3** A write whose `idem` the daemon keeps for the same method MUST be answered with the answer
kept, result or error, without being carried out again; one whose first call is still being carried
out MUST be answered once that call is answered.

**6.7.4** A write whose `idem` the daemon keeps for another method MUST be refused 409, `That idem
key was used for another method.`

### 6.8. Subscriptions

**6.8.1** `epic.attach` and `notices.subscribe` MUST each open a subscription and answer with its
`sub`, a text unique within the session.

**6.8.2** The daemon MUST send each message of an epic subscription as the notification `epic.event`
`{sub, message}`, `message` a message of Section 4.9 of [DAEMON], and each notice of a notices
subscription as `notices.event` `{sub, notice}`, in the order they happen.

**6.8.3** A subscription MUST end with `epic.detach` or `notices.unsubscribe`, when an epic
subscription is sent `gone`, and when its session closes; a call naming a `sub` that is not open on
the session MUST be refused 410.

**6.8.4** `epic.attach` with `since` `{epoch, seq}` MUST send, in place of the whole history, the
history records after `seq`, where `epoch` is the host's current `epoch` (Section 4.9.1.3 of
[DAEMON]) and every record after `seq` is still kept; otherwise it MUST send every record kept, as
`replay` `true` does.

**6.8.5** `notices.subscribe` with `after` MUST send every notice kept after that id before any new
one.

### 6.9. Files

**6.9.1** A read handle MUST be made by a method that answers one (`runs.bundle`, Section 4.16 of
[DAEMON]); a write handle MUST be made by `files.create` `{name, size}`, `name` the file's name and
`size` its length in bytes, at most 2 147 483 648.

**6.9.2** `files.read` `{handle, offset, length}` MUST answer `data`, the base64 of the bytes of the
file from `offset`, at most `length` and at most 1 048 576 of them, and `eof`, whether they reach
its end.

**6.9.3** `files.write` `{handle, offset, data}` MUST append the base64-decoded `data`, at most
1 048 576 bytes, where `offset` is the length written so far, and answer `size`, the length written;
another `offset` MUST be refused 409, `Write at <size>.`, and bytes past the `size` declared 413.

**6.9.4** A handle MUST belong to the session that made it, MUST end with that session, with
`files.close` `{handle}`, after 600 seconds unused, or once the method it was given to has taken it,
and MUST then be removed from this machine with what it held.

**6.9.5** A handle that is not open on the session MUST be refused 404, `There is no file
<handle>.`

### 6.10. Limits and backpressure

**6.10.1** The daemon MUST NOT wait on a slow session: it MUST keep one queue of the frames it sends
each session, responses and notifications alike, in the order sent, and where more than 64 MiB wait
in it, it MUST drop the notifications among them, keeping every response, and MUST end every epic
subscription of the session with `gone` `too far behind; attach again` and every notices
subscription with `notices.event` `{sub, gone: "too far behind; subscribe again"}`, sent after the
frame in progress.

**6.10.2** A result or notification whose frame would exceed Section 6.3.2 MUST NOT be sent: a
result MUST be replaced by the error 413, `That is more than an answer here may carry.`, and a
notification MUST be dropped and written to `daemon.log`.

**6.10.3** A call whose frame exceeds Section 6.3.2 MUST close the session; a client MUST NOT send
one, and MUST instead refuse it itself, sending nothing, with 413, `That is more than a call here
may carry.`

### 6.11. The OpenRPC document

**6.11.1** [OPENRPC] MUST be an OpenRPC 1.3 document [OPENRPC-SPEC] listing every method the daemon
serves, each with `paramStructure` `by-name`, the JSON Schema of each parameter and of its result,
and the errors it answers; a method it does not list MUST NOT be served.

**6.11.2** OpenRPC has no object for a notification the server sends; [OPENRPC] MUST list each under
the extension `x-notifications` of its root, an array of objects holding `name`, `summary` and
`params` as a method object holds them, and no `result`. A notification the client sends,
`session.cancel`, MUST be listed among the methods with the extension `x-notification` `true`, and
no `result` and no `errors`, since it is never answered.

**6.11.3** Every method but `session.cancel` MUST list, beside its own errors, -32600, -32602,
-32603, -32800 and 413, and, but for `session.hello`, `pair.claim` and `rpc.discover`, 401.

**6.11.4** `rpc.discover` MUST answer [OPENRPC] as the daemon serves it, its `info.version` the
daemon's protocol version.

**6.11.5** Where [OPENRPC] and a document of the protocol disagree on a method's parameters or
result, the document of the protocol MUST state the intended behaviour, as Section 2.2.7 of [CORE]
states.

**6.11.6** Every method of [OPENRPC] MUST carry the extensions `x-hmz-reach` and `x-hmz-writes`, as
Section 4.21.2 of [DAEMON] defines them.

**6.11.7** A parameter or a member of a result that [OPENRPC] marks `deprecated` is one no document
of the protocol states: a client MUST NOT send it and MUST NOT read it, and a daemon MAY take it
and MAY answer it.

## 7. Security Considerations

This section states no requirement of its own. It names the properties stated elsewhere in this
document on which the security of a user's machine and work depends.

- **Trusted carriers.** A Unix socket, `ssh` and WSL already admit the client as the daemon's user,
  so frames go directly over them (Section 3.5.1 and Section 3.5.3). Every other carrier, `wss` and
  a relay behind TLS included, carries frames only inside mutual TLS or a pinned WebRTC data channel
  (Section 3.5.2, Section 3.5.3 and Section 3.5.5).
- **Pinning.** A client checks that the daemon's certificate has the SPKI fingerprint it pins, and
  pins only an id a pairing code or a trusted carrier gave it (Section 4.4.4 and Section 4.4.7). No
  certificate authority, name or validity period is trusted (Section 4.4.3). A daemon identifies a
  client by its certificate's fingerprint alone (Section 4.4.5).
- **Pairing.** A pairing code carries 256 random bits, lives 600 seconds unless asked otherwise and
  is claimed once; the token is held only in the daemon's memory and compared in constant time
  (Section 4.5.3, Section 4.5.4, Section 4.5.6 and Section 4.5.9). Whoever holds a code before it is
  claimed can pair; the code is therefore a secret until claimed. An unpaired session can call only
  `session.hello`, `pair.claim` and `rpc.discover` (Section 4.5.10). A paired device is whole, as a
  frontend over the socket is (Section 5 of [DAEMON]).
- **Revocation.** Revoking a device closes its live sessions at once (Section 4.6.3).
- **Scoped links.** A session over the scoped link of an Ai-chan conversation is admitted as one
  over a trusted carrier, but is held to that conversation's reach and is not whole (Section 4.21
  of [DAEMON] and Section 4.22.6 of [DAEMON]).
- **WebRTC.** Signalling crosses the relay and is not trusted: the daemon signs both DTLS
  fingerprints with its device key, and the browser checks that signature against the daemon id it
  pins before any frame (Section 4.7.5 and Section 4.7.6); the daemon identifies the browser by the
  DTLS fingerprint DTLS holds it to (Section 4.7.7).
- **The relay.** The relay is untrusted by design. It proves that a registering daemon holds the key
  of its id, so that nobody else takes its room (Section 5.4.3), but it never holds a key that could
  read or alter a session: what it splices is TLS or DTLS end to end (Section 5.5.3 and Section
  4.7). It learns which daemon ids register, which addresses join them, when and how many bytes, and
  keeps none of it (Section 5.5.6).
- **Limits.** Frames, relay messages, chunks and queued notifications are bounded (Section 6.3.2,
  Section 5.6.1, Section 6.9 and Section 6.10.1), and the relay closes a connection that says
  nothing in time (Section 5.3.5), so that one peer cannot hold up the daemon, the relay or another
  session (Section 6.4.6).
- **Keys.** A device's private key never leaves it and is never on a command line (Section 4.3.4);
  its files are readable by the user alone (Section 4.14 of [FILES]).

## 8. References

### 8.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[RFC3986]** Berners-Lee, T., Fielding, R., and L. Masinter, "Uniform Resource Identifier (URI):
  Generic Syntax", STD 66, RFC 3986, January 2005, <https://www.rfc-editor.org/info/rfc3986>.
- **[RFC4648]** Josefsson, S., "The Base16, Base32, and Base64 Data Encodings", RFC 4648, October
  2006, <https://www.rfc-editor.org/info/rfc4648>.
- **[RFC5280]** Cooper, D., et al., "Internet X.509 Public Key Infrastructure Certificate and
  Certificate Revocation List (CRL) Profile", RFC 5280, May 2008,
  <https://www.rfc-editor.org/info/rfc5280>.
- **[RFC6455]** Fette, I. and A. Melnikov, "The WebSocket Protocol", RFC 6455, December 2011,
  <https://www.rfc-editor.org/info/rfc6455>.
- **[RFC7301]** Friedl, S., et al., "Transport Layer Security (TLS) Application-Layer Protocol
  Negotiation Extension", RFC 7301, July 2014, <https://www.rfc-editor.org/info/rfc7301>.
- **[RFC8446]** Rescorla, E., "The Transport Layer Security (TLS) Protocol Version 1.3", RFC 8446,
  August 2018, <https://www.rfc-editor.org/info/rfc8446>.
- **[RFC8831]** Jesup, R., Loreto, S., and M. Tüxen, "WebRTC Data Channels", RFC 8831, January
  2021, <https://www.rfc-editor.org/info/rfc8831>.
- **[RFC8832]** Jesup, R., Loreto, S., and M. Tüxen, "WebRTC Data Channel Establishment Protocol",
  RFC 8832, January 2021, <https://www.rfc-editor.org/info/rfc8832>.
- **[FIPS186-5]** National Institute of Standards and Technology, "Digital Signature Standard
  (DSS)", FIPS 186-5, February 2023, <https://doi.org/10.6028/NIST.FIPS.186-5>.
- **[JSONRPC]** JSON-RPC Working Group, "JSON-RPC 2.0 Specification", January 2013,
  <https://www.jsonrpc.org/specification>.
- **[SEMVER]** Preston-Werner, T., "Semantic Versioning 2.0.0",
  <https://semver.org/spec/v2.0.0.html>.
- **[OPENRPC-SPEC]** OpenRPC, "OpenRPC Specification 1.3.2",
  <https://spec.open-rpc.org/>.
- **[OPENRPC]** "The Humanize Protocol: OpenRPC Document", [`openrpc.json`](openrpc.json).
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[DESKTOP]** "The Humanize Protocol: Desktop Application", [`desktop.md`](desktop.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).
