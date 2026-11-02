"""Reaching a daemon on another machine over EasyTier, with neither root nor a TUN device.

`ssh` reaches a machine somebody can log in to. EasyTier reaches one that nobody can: two
`easytier-core` that know one network name and one network secret find each other through a
shared node, punch through whatever NAT is between them, and fall back to being relayed by that
node where they cannot. EasyTier runs no such node of its own any more, so hmz names none: each
end is told the nodes the user chose, and two ends meet only where they name one in common.
:func:`community` reads the nodes the community shares, and how each has stood, from the Uptime
Kuma status page EasyTier's own apps read (Astral, EasytierGame); `HUMANIZE_EASYTIER_NODES`
names another Uptime Kuma server to read its page `easytier` from instead.

Humanize runs one `easytier-core` on each end -- :func:`serving` beside `hmz server`,
:func:`joining` beside whoever opens it -- and neither needs anything installed: :func:`binary`
downloads the release pinned here from EasyTier's own GitHub releases, checks it against the
SHA-256 pinned beside it, and keeps it under `~/.hmz/easytier/<VERSION>/`.

Neither end makes a TUN device, which is what would need root. With `--no-tun` the serving end
still answers the fixed virtual address it is given, and what reaches it there on a TCP port is
connected to the same port on its own loopback -- so the web `hmz server` keeps on
`127.0.0.1:<PORT>` is reachable at `<address>:<PORT>` by every member of the network, and by no
port else, since `--tcp-whitelist` lets only that one through and `--udp-whitelist` none. The
joining end takes an address of the network's own by DHCP and forwards a port on its loopback
to that one with `--port-forward`, which EasyTier carries in user space; its own loopback it
lets nothing reach, which no-tun would otherwise open to the network as the serving end's is.
Both were checked against 2.6.4: a `curl` of the joining end's port answered by a server bound
to the serving end's loopback, and one of the serving end's own forward to the joining end's
loopback refused. Each listens on a port of its own on every interface, which is what lets two
ends that can reach each other connect directly rather than through the public node; a node
that does not know the secret is refused there.

What the user types is one secret, and it never leaves the machine. The network's name and its
secret are each a SHA-256 of it under a label of their own, so a public node learns a name and
a proof of membership but nothing that opens the web; the web's key is an HMAC of it under a
third. The derived secret is handed to `easytier-core` in its environment
(`ET_NETWORK_SECRET`), never on its command line, where any user of the machine could read it.

`HUMANIZE_EASYTIER` names a binary to run instead of the downloaded one -- one installed by a
package manager, or the stand-in this suite runs. EasyTier reads every flag from an `ET_`
variable too, so none of those this process has is passed on: what it is told is what is here.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, cast

from hmz import home

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = [
    "NODES",
    "PEERS",
    "PORT",
    "SHA256",
    "VERSION",
    "WHICH",
    "Node",
    "binary",
    "checked",
    "community",
    "joining",
    "key",
    "network",
    "node",
    "serving",
]

#: The release of EasyTier that is downloaded.
VERSION = "2.6.4"

#: What names a binary to run instead of downloading one.
WHICH = "HUMANIZE_EASYTIER"

#: The port `hmz server` keeps its web on, on its loopback and so at the network's address.
PORT = 41817

#: The shared nodes hmz names of its own: none, so every caller names those the user chose.
PEERS: tuple[str, ...] = ()

#: The most of a status page that is read.
_MOST = 4 * 1024 * 1024

#: What names the Uptime Kuma server the community's shared nodes are read from.
NODES = "HUMANIZE_EASYTIER_NODES"

#: The Uptime Kuma server EasyTier's own apps read the community's shared nodes from.
_KUMA = "https://easytier.gd.nkbpal.cn"

#: Its status page that lists them.
_PAGE = "easytier"

#: The protocols a node may be reached over, as EasyTier names them in a URL.
_PROTOCOLS = frozenset({"tcp", "udp", "ws", "wss", "quic", "wg"})

#: A node's host and port, as a monitor's name says them: an IPv4 address or a domain.
_HOST = r"(?:(?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9][-A-Za-z0-9.]*\.[A-Za-z]+):\d{1,5}"
_ADDRESS = re.compile(_HOST)

#: A node's URL, as a monitor's name may say it whole.
_LINK = re.compile(
    rf"(?<![A-Za-z])({'|'.join(sorted(_PROTOCOLS))})://({_HOST})(?![-\w.:])",
    re.IGNORECASE,
)

#: A version, as a monitor's name says one.
_RELEASE = re.compile(r"v?\d+(?:\.\d+){1,3}(?:[-+][\w.-]+)?")

#: The address the serving end has in the network; every joining end takes one by DHCP.
_SERVER = "10.144.144.1"

#: Each release asset there is, by `platform.system()` and `platform.machine()`, lowercased.
_ASSETS = {
    ("darwin", "arm64"): "macos-aarch64",
    ("darwin", "x86_64"): "macos-x86_64",
    ("linux", "x86_64"): "linux-x86_64",
    ("linux", "amd64"): "linux-x86_64",
    ("linux", "aarch64"): "linux-aarch64",
    ("linux", "arm64"): "linux-aarch64",
    ("windows", "amd64"): "windows-x86_64",
    ("windows", "x86_64"): "windows-x86_64",
}

#: The SHA-256 of the release's zip for each platform, as it was downloaded.
SHA256 = {
    "macos-aarch64": "4be1882d1aa36d31c1d6ba0596f2cf8a097e371f8da124212324b2e0f8df7e4b",
    "macos-x86_64": "89fc28a6e6995259d76ce3f11775220e8a21c760e94df91a6a9db30a69b6982e",
    "linux-x86_64": "61b659eaedba658fa66fe47d17e1426cdd77e5d02fa15fed447bb4357c09dfd6",
    "linux-aarch64": "f533ec25a7ea714e09f645615012200278058525795cc3bb690ff011aec1a70f",
    "windows-x86_64": "27af91e270e554709b048bd32327fefd2dfce5062ae1e8701af7550c6f525f84",
}

#: Where a release's assets are downloaded from.
_RELEASES = "https://github.com/EasyTier/EasyTier/releases/download"

#: How long the download may go without a byte.
_WAITING = 60.0

#: The fewest bytes a secret may be.
_FEWEST = 16


@dataclass(frozen=True)
class Node:
    """A shared EasyTier node of the community's, and how it has stood.

    Attributes:
      url: What EasyTier is told to reach it by, as `tcp://host:port`.
      name: What its monitor is named: where it is, who runs it, its version and its address.
      version: The EasyTier it runs, or empty where its name does not say.
      up: Whether it answered last; None where that is unknown.
      uptime: The share of the last 24 hours it was up, from 0 to 1; None where unknown.
    """

    url: str
    name: str
    version: str
    up: bool | None
    uptime: float | None


def community(timeout: float = 10) -> list[Node]:
    """The shared nodes of EasyTier's community, as its status page lists them.

    A monitor whose name says no `host:port` is left out, and a node listed twice is listed
    once. The page's heartbeats say how each has stood; where they cannot be read, every node
    is listed with `up` and `uptime` None.

    Args:
      timeout: How long each of the two reads may take, in seconds.

    Returns:
      Each node, in the order the page lists them.

    Raises:
      OSError: If the page cannot be read or is not a status page.
    """
    base = (os.environ.get(NODES) or _KUMA).rstrip("/")
    page = _read(f"{base}/api/status-page/{_PAGE}", timeout)
    if not isinstance(_at(page, "publicGroupList"), list):
        msg = f"{base} has no status page {_PAGE}"
        raise OSError(msg)
    try:
        beats = _read(f"{base}/api/status-page/heartbeat/{_PAGE}", timeout)
    except OSError:
        beats = None
    nodes: dict[str, Node] = {}
    for group in _each(_at(page, "publicGroupList")):
        for monitor in _each(_at(group, "monitorList")):
            node = _node(monitor, beats)
            if node is not None and node.url not in nodes:
                nodes[node.url] = node
    return list(nodes.values())


def checked(secret: str) -> str:
    """A secret, where it is long enough to be one.

    Raises:
      ValueError: If it is fewer than 16 bytes of UTF-8.
    """
    if len(secret.encode("utf-8")) < _FEWEST:
        msg = "A secret must be at least 16 bytes."
        raise ValueError(msg)
    return secret


def node(url: str) -> str:
    """A shared node's URL, where it is one: `<protocol>://<host>:<port>`.

    Raises:
      ValueError: If its protocol is not one EasyTier reaches a node over (`tcp`, `udp`, `ws`,
        `wss`, `quic`, `wg`), or it says no host or no port.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        port = None
    else:
        if parts.scheme not in _PROTOCOLS or not parts.hostname:
            port = None
    if port is None or url != url.strip():
        msg = f"{url!r} is not an EasyTier node, as tcp://host:port."
        raise ValueError(msg)
    return url


def network(secret: str) -> tuple[str, str]:
    """The name and the secret of the EasyTier network a secret stands for.

    Returns:
      Each a SHA-256 of the secret under a label of its own, in hex.
    """
    return _derived("hmz-easytier-name", secret), _derived(
        "hmz-easytier-secret", secret
    )


def key(secret: str) -> str:
    """The key the web served over the network a secret stands for is opened with."""
    return hmac.new(secret.encode("utf-8"), b"hmz-web-key", hashlib.sha256).hexdigest()


def binary(say: Callable[[str], object] | None = None) -> Path:
    """The `easytier-core` to run, downloaded the first time it is asked for.

    Args:
      say: What is told, as it happens, that a download is under way.

    Returns:
      What `HUMANIZE_EASYTIER` names, or else the one kept under Humanize's home.

    Raises:
      OSError: If there is none and one cannot be downloaded: this machine is one EasyTier
        has no release for, the network failed, or what was downloaded is not what was
        pinned.
    """
    said = os.environ.get(WHICH)
    if said and (named := Path(said).expanduser()).is_file():
        return named
    kept = home() / "easytier" / VERSION
    core = kept / ("easytier-core.exe" if sys.platform == "win32" else "easytier-core")
    if core.is_file():
        return core
    asset = _ASSETS.get((platform.system().lower(), platform.machine().lower()))
    if asset is None:
        msg = (
            f"EasyTier has no release for {platform.system()} {platform.machine()}; "
            f"install easytier-core and name it in {WHICH}"
        )
        raise OSError(msg)
    if say is not None:
        say(f"Downloading EasyTier {VERSION}")
    kept.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=kept, prefix=".download-") as scratch:
        archive = Path(scratch) / "easytier.zip"
        _downloaded(asset, archive)
        _unpacked(archive, Path(scratch), kept, core.name)
    return core


def serving(
    secret: str,
    port: int = PORT,
    *,
    peers: Sequence[str],
    out: int | IO[bytes] | None = subprocess.DEVNULL,
) -> subprocess.Popen[bytes]:
    """Starts the `easytier-core` that lets the network reach this machine's loopback port.

    Args:
      secret: What the network is joined with.
      port: The port on this machine's loopback it reaches, and the only one.
      peers: The shared nodes it meets the others through, at least one.
      out: Where what it says goes.

    Returns:
      It, running until it is stopped.

    Raises:
      OSError: If there is no `easytier-core` to start, as :func:`binary` says.
      ValueError: If the secret is too short to be one, or no node is named.
    """
    return _started(
        secret,
        ["--ipv4", _SERVER, "--tcp-whitelist", str(port), "--udp-whitelist", "0"],
        peers,
        out,
    )


def joining(
    secret: str,
    local: int,
    *,
    port: int = PORT,
    peers: Sequence[str],
    out: int | IO[bytes] | None = subprocess.DEVNULL,
) -> subprocess.Popen[bytes]:
    """Starts the `easytier-core` that puts the serving machine's port on this one's loopback.

    Args:
      secret: What the network is joined with.
      local: The port on this machine's loopback it is put on.
      port: The serving machine's port.
      peers: The shared nodes it meets the others through, at least one.
      out: Where what it says goes.

    Returns:
      It, running until it is stopped.

    Raises:
      OSError: If there is no `easytier-core` to start, as :func:`binary` says.
      ValueError: If the secret is too short to be one, or no node is named.
    """
    return _started(
        secret,
        [
            "--dhcp",
            "true",
            "--tcp-whitelist",
            "0",
            "--udp-whitelist",
            "0",
            "--port-forward",
            f"tcp://127.0.0.1:{local}/{_SERVER}:{port}",
        ],
        peers,
        out,
    )


def _started(
    secret: str,
    told: list[str],
    peers: Sequence[str],
    out: int | IO[bytes] | None,
) -> subprocess.Popen[bytes]:
    """Starts `easytier-core` in the network a secret stands for, without a TUN device."""
    name, hidden = network(checked(secret))
    if not peers:
        msg = "An EasyTier daemon needs at least one node."
        raise ValueError(msg)
    for one in peers:
        node(one)
    argv = [
        str(binary()),
        "--network-name",
        name,
        "--no-tun",
        "true",
        "--private-mode",
        "true",
        "--listeners",
        "tcp://0.0.0.0:0",
        "udp://0.0.0.0:0",
        *told,
        "--peers",
        *peers,
    ]
    return subprocess.Popen(
        argv,
        env={
            **{
                one: said
                for one, said in os.environ.items()
                if not one.startswith("ET_")
            },
            "ET_NETWORK_SECRET": hidden,
        },
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=out,
    )


def _read(url: str, timeout: float) -> object:
    """What an Uptime Kuma server answers at a URL, as JSON.

    Raises:
      OSError: If it is not an http one, cannot be read, or is not JSON.
    """
    if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        msg = f"{url} is not an http URL"
        raise OSError(msg)
    try:
        asked = urllib.request.Request(url, headers={"User-Agent": "humanize"})  # noqa: S310
        with urllib.request.urlopen(asked, timeout=timeout) as answer:  # noqa: S310
            # One longer than the most is cut short, and so not JSON.
            return json.loads(answer.read(_MOST))
    except (OSError, http.client.HTTPException, ValueError) as why:
        msg = f"cannot read {url}: {why}"
        raise OSError(msg) from why


def _node(monitor: object, beats: object) -> Node | None:
    """The node a monitor of the status page watches, or None where its name says no address.

    Its name is `/`-separated parts -- where it is, who runs it, its version, its address --
    of which the address is a node's URL where the name says one whole, and else the part
    that is `host:port`; a part that is a protocol says that is reached over it, and
    otherwise it is reached over TCP.
    """
    named, ident = _at(monitor, "name"), _at(monitor, "id")
    if not isinstance(named, str) or not isinstance(ident, (int, str)):
        return None
    parts = [part.strip() for part in named.split("/")]
    if linked := _LINK.search(named):
        url = f"{linked[1]}://{linked[2]}".lower()
    else:
        address = next((part for part in parts if _ADDRESS.fullmatch(part)), None)
        if address is None:
            return None
        said = [part.lower() for part in parts if part.lower() in _PROTOCOLS]
        url = f"{said[0] if said else 'tcp'}://{address.lower()}"
    heard = _each(_at(_at(beats, "heartbeatList"), str(ident)))
    status = _at(heard[-1], "status") if heard else None
    uptime = _at(_at(beats, "uptimeList"), f"{ident}_24")
    return Node(
        url=url,
        name=named.strip(),
        version=next((part for part in parts if _RELEASE.fullmatch(part)), ""),
        up={1: True, 0: False}.get(status) if type(status) is int else None,
        uptime=(
            min(max(float(uptime), 0.0), 1.0)
            if isinstance(uptime, (int, float)) and not isinstance(uptime, bool)
            else None
        ),
    )


def _at(held: object, key: str) -> object:
    """What a JSON object holds under a key; None where it is not an object or holds none."""
    return cast("dict[str, object]", held).get(key) if isinstance(held, dict) else None


def _each(held: object) -> list[object]:
    """What a JSON array holds; nothing where it is not an array."""
    return cast("list[object]", held) if isinstance(held, list) else []


def _derived(label: str, secret: str) -> str:
    """A SHA-256 of a secret under a label, so that no two labels say the same."""
    return hashlib.sha256(f"{label}\0{secret}".encode()).hexdigest()


def _downloaded(asset: str, into: Path) -> None:
    """Downloads a release asset and checks it is the one pinned.

    Raises:
      OSError: If it cannot be, or it is not.
    """
    url = f"{_RELEASES}/v{VERSION}/easytier-{asset}-v{VERSION}.zip"
    digest = hashlib.sha256()
    try:
        asked = urllib.request.Request(url, headers={"User-Agent": "humanize"})  # noqa: S310
        with (
            urllib.request.urlopen(asked, timeout=_WAITING) as answer,  # noqa: S310
            into.open("wb") as writing,
        ):
            while chunk := answer.read(1 << 20):
                digest.update(chunk)
                writing.write(chunk)
    except (OSError, http.client.HTTPException) as why:
        msg = f"cannot download EasyTier {VERSION} from {url}: {why}"
        raise OSError(msg) from why
    if digest.hexdigest() != SHA256[asset]:
        msg = (
            f"EasyTier {VERSION} from {url} is not the one pinned: its SHA-256 differs"
        )
        raise OSError(msg)


def _unpacked(archive: Path, scratch: Path, kept: Path, core: str) -> None:
    """Takes `easytier-core`, and on Windows the libraries it loads, out of a release.

    Each is moved into place whole, the binary last, so that one found there is one whose
    libraries are there too, whoever else is unpacking the same release at the same time.

    Raises:
      OSError: If the archive is not a release with that binary in it.
    """
    try:
        with zipfile.ZipFile(archive) as zipped:
            wanted = [
                one
                for one in zipped.infolist()
                if Path(one.filename).name == core
                or Path(one.filename).suffix.lower() == ".dll"
            ]
            if not any(Path(one.filename).name == core for one in wanted):
                msg = f"EasyTier {VERSION} has no {core}"
                raise OSError(msg)
            wanted.sort(key=lambda one: Path(one.filename).name == core)
            for one in wanted:
                name = Path(one.filename).name
                taken = scratch / f"{name}.new"
                with zipped.open(one) as reading, taken.open("wb") as writing:
                    shutil.copyfileobj(reading, writing)
                taken.chmod(
                    taken.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
                try:
                    taken.replace(kept / name)
                except OSError:
                    # One already there and running, as Windows will not replace.
                    if not (kept / name).is_file():
                        raise
    except zipfile.BadZipFile as why:
        msg = f"EasyTier {VERSION} is not a zip: {why}"
        raise OSError(msg) from why
