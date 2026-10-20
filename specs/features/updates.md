# Updates

## 1. Scope

This specification defines how **hmz** learns which release of itself is newest, how the
terminal and web interfaces tell the **user** that a newer release exists, and how `hmz update`
moves the installation of hmz to the newest release.

Out of scope:

- Updating installed flows from a flowverse (`features/tui.md`, `features/web.md`).
- The desktop app's own update (`features/desktop.md`).
- The location of the kept release record (`api/files/machine.md`).
- The command-line syntax of `hmz update` (`api/cli.md`).

## 2. Definitions

**2.1** **Running version**: the version of hmz executing in the current process.

**2.2** **Newest release**: the newest release of the `hmz` package on PyPI that is not a
pre-release, as the `info.version` field of `https://pypi.org/pypi/hmz/json` states.

**2.3** **Release source**: where hmz asks for the newest release: the URL of §2.2, or the URL or
file named by the environment variable `HUMANIZE_RELEASES`.

**2.4** **Kept release**: the newest release as hmz last fetched it, kept for **this machine**.

**2.5** **Stale**: the state of the kept release when it is absent or was written more than 24
hours ago.

**2.6** **Newer release**: the kept release where it is greater than the running version by
version ordering; a running version of `0.0.0` or `unknown` has no newer release.

**2.7** **Installer**: the program that installed hmz: `uv tool`, `pipx`, `pip`, or uv's `pip`.

## 3. Learning the newest release

### 3.1 Fetching

**3.1.1** hmz MUST fetch the newest release from the release source, and MUST NOT fetch it where
`HUMANIZE_RELEASES` is `off`, `0`, `no`, `none` or empty, ignoring case.

**3.1.2** A fetch MUST send no data about the user, the machine or any workspace beyond what an
HTTP request to the release source requires.

**3.1.3** A fetch MUST give up after 10 seconds, and MUST treat a source that does not answer, or
answers with no valid version, as having no newest release.

**3.1.4** A successful fetch MUST replace the kept release.

**3.1.5** A failed fetch MUST leave the kept release unchanged and MUST NOT raise an error to any
interface.

### 3.2 Interfaces

**3.2.1** The terminal interface MUST, when it starts, fetch the newest release where the kept
release is stale, without delaying any input or drawing.

**3.2.2** The terminal interface MUST then state once in its transcript, where there is a newer
release, that the newer release is out and that `hmz update` updates to it.

**3.2.3** `hmz web` MUST, when it starts, fetch the newest release in the background where the
kept release is stale.

**3.2.4** The web interface MUST, while there is a newer release, mark this machine as having one
and offer `Update` in its menu, which copies `hmz update` for the user to run.

**3.2.5** An interface MUST NOT fetch the newest release more than once in 24 hours while the
previous fetch succeeded.

**3.2.6** An interface MUST NOT install a release itself.

## 4. `hmz update`

### 4.1 Choosing the installer

**4.1.1** `hmz update` MUST choose the installer, and make the refusals of §4.2.1 to §4.2.3,
before it asks for the newest release.

**4.1.2** `hmz update` MUST then fetch the newest release, whether or not the kept release is stale.
While it fetches, where standard error is a terminal and escapes are allowed (`api/cli.md` §4.2),
it MUST draw a transient spinner there saying that PyPI is being asked, and MUST take it down once
PyPI answers or cannot be asked.

**4.1.3** Where hmz was installed by `uv tool`, `hmz update` MUST run `uv tool upgrade hmz`.

**4.1.4** Where hmz was installed by `pipx`, `hmz update` MUST run `pipx upgrade hmz`.

**4.1.5** Where hmz was installed otherwise, `hmz update` MUST run `pip install --upgrade` with
the Python executing hmz, or uv's `pip install --upgrade` against that Python where pip is not
installed in it, naming `hmz` with every extra whose packages are all installed.

**4.1.6** `hmz update` MUST keep the extras hmz was installed with.

### 4.2 Refusals

**4.2.1** `hmz update` MUST NOT run any installer, MUST state why, and MUST exit 1 where hmz is
not installed as a package.

**4.2.2** `hmz update` MUST NOT run any installer, MUST state why naming the source, and MUST exit
1 where hmz was installed from a checkout or a URL rather than from PyPI.

**4.2.3** `hmz update` MUST NOT run any installer, MUST state why, and MUST exit 1 where the
installer §4.1 chose is `uv` or `pipx` and is not on `PATH`.

**4.2.4** `hmz update` MUST NOT run any installer, MUST state why, and MUST exit 1 where the
release source cannot be asked.

### 4.3 Outcome

**4.3.1** Where the running version is already the newest release or newer, `hmz update` MUST
state so, MUST run nothing, and MUST exit 0.

**4.3.2** Before it runs the installer, `hmz update` MUST state the running version, the newest
release and the command it runs.

**4.3.3** Where the installer exits with a non-zero status, `hmz update` MUST state so and MUST
exit 1.

**4.3.4** Where the installer leaves a version other than the newest release installed,
`hmz update` MUST state the version left and MUST exit 1.

**4.3.5** Where the newest release is installed, `hmz update` MUST state so and MUST exit 0.

### 4.4 Running processes

**4.4.1** `hmz update` MUST NOT stop, restart or signal any running hmz process, including a
**daemon**.

**4.4.2** Where a daemon holds the epics of this machine, `hmz update` MUST state, after a
successful update, that those epics run the release the daemon started under until the daemon
stops.

> Informative: a process keeps executing the code it loaded; the new release takes effect in
> processes started after the update.
