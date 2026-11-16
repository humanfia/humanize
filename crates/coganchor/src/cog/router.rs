//! Where each path an agent names is answered: the mirror (and so the target), or this
//! machine. Port of `Router`/`Layout` in `hmz.coganchor.policy`. [Unit 8]
//!
//! Three independent questions:
//!
//! * **Paths.** A [`Layout`] maps a directory on this machine (the mirror) onto the path it
//!   occupies on the target. A target that spells a path more than one way -- a Mac reaches
//!   `/tmp` through `/private/tmp` and ignores case besides -- is met by
//!   [`Router::canonical`], which settles on this machine's spelling before anything is
//!   matched, mirrored or created.
//! * **Programs.** Everything the agent spawns runs on the target, except the agent's own
//!   runtime, listed in `local_programs`.
//! * **Redirects.** A path may be answered with another ([`Router::swap`]).

use std::borrow::Cow;
use std::path::PathBuf;
use std::sync::OnceLock;

use crate::cog::policy;
use crate::cog::statepaths::{abspath, expanduser, join};
use crate::proto::{
    CASE_INSENSITIVE, path_key, path_spellings, path_within, rewrite_path_prefix, spelled_twice,
};

/// A mirror on this machine and the workspace on the target it stands for.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Layout {
    pub shadow: PathBuf,
    /// The workspace as the target names it; empty for the mirror's own path.
    pub workspace: String,
}

impl Layout {
    /// A layout with both roots normalised, the target's path being the mirror's own where
    /// none is given (`Layout.create`).
    pub fn create(shadow: &str, workspace: Option<&str>) -> Layout {
        let local = normalise(shadow);
        let workspace = match workspace {
            Some(one) if !one.is_empty() => normalise(one),
            _ => local.clone(),
        };
        Layout {
            shadow: PathBuf::from(local),
            workspace,
        }
    }

    /// The mirror's root, as a string.
    pub fn local_root(&self) -> Cow<'_, str> {
        self.shadow.to_string_lossy()
    }

    /// The target's root: the workspace, or the mirror's own path where that is empty.
    pub fn virtual_root(&self) -> Cow<'_, str> {
        if self.workspace.is_empty() {
            self.local_root()
        } else {
            Cow::Borrowed(&self.workspace)
        }
    }

    /// What of `path` lies inside the mirror (`""` for the root), or `None` if it is outside.
    pub fn below(&self, path: &str, insensitive: bool) -> Option<String> {
        path_within(path, &self.local_root(), insensitive)
    }

    /// Whether `path` lies inside the mirror.
    pub fn contains(&self, path: &str, insensitive: bool) -> bool {
        self.below(path, insensitive).is_some()
    }

    /// `path` as the target names it (`Layout.to_virtual`): the part below the root found
    /// by its characters where they settle it, and by folding case where they do not --
    /// whoever asks has already decided the path is the mirror's. `None` for a path not
    /// inside this layout at all.
    pub fn to_virtual(&self, path: &str) -> Option<String> {
        let suffix = self.below(path, false).or_else(|| self.below(path, true))?;
        let root = self.virtual_root();
        Some(if suffix.is_empty() {
            root.into_owned()
        } else {
            join(&root, &suffix)
        })
    }
}

/// What a router is built from.
#[derive(Clone, Debug, Default)]
pub struct RouterConfig {
    pub layouts: Vec<Layout>,
    /// Other names the mirror is reached by (a peer target's, a symlinked mirror's), as
    /// `(the name, the root it names)`.
    pub aliases: Vec<(String, String)>,
    /// Paths that stay on this machine: the agent's state, its home, `--local-path`s.
    pub local_paths: Vec<String>,
    /// Programs that run on this machine: the agent's own, `--local-exec`s.
    pub local_programs: Vec<String>,
    /// `--redirect FROM=TO`, absolute.
    pub redirects: Vec<(String, String)>,
}

/// Where a path lands.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Place {
    /// In the mirror: its path here, and the path the target knows it by.
    Mirror {
        local: PathBuf,
        virtual_path: String,
    },
    /// On this machine, as named.
    Local,
}

/// The routing decisions of one session.
#[derive(Debug)]
pub struct Router {
    /// Longest root first, so nested layouts win over their parents.
    layouts: Vec<Layout>,
    aliases: Vec<(String, String)>,
    local_paths: Vec<String>,
    local_programs: Vec<String>,
    /// Longest named path first, so a path under two takes the one that says most.
    redirects: Vec<(String, String)>,
    /// What the target said it is at the handshake; unset until then.
    platform: OnceLock<String>,
    /// What [`Router::settles`] came to once the platform was known; never the answer of
    /// before the handshake.
    settled: OnceLock<bool>,
}

impl Router {
    /// A router; the target's platform is learnt later ([`Router::learn_platform`]).
    /// Normalises and orders its settings as `Router.__post_init__` does, and normalises
    /// each layout as `Layout.create` would, its fields being public to build by hand.
    pub fn new(config: RouterConfig) -> Router {
        let mut layouts: Vec<Layout> = config
            .layouts
            .iter()
            .map(|one| {
                Layout::create(
                    &one.local_root(),
                    Some(&one.workspace)
                        .filter(|w| !w.is_empty())
                        .map(String::as_str),
                )
            })
            .collect();
        // Measured as the roots are matched: a root written the long way round is no deeper.
        layouts.sort_by_key(|one| {
            std::cmp::Reverse(path_key(&one.local_root(), false).chars().count())
        });
        let aliases: Vec<(String, String)> = config
            .aliases
            .iter()
            .map(|(name, root)| (normalise(name), normalise(root)))
            .collect();
        let mut redirects: Vec<(String, String)> = config
            .redirects
            .iter()
            .map(|(named, instead)| (normalise(named), normalise(instead)))
            .collect();
        redirects.sort_by_key(|(named, _)| std::cmp::Reverse(named.chars().count()));
        // A hole written as the workspace's own path is a hole in the mirror that path now
        // reaches, and a program kept here is the program in the mirror, for the same reason.
        let mut local_paths = config.local_paths.clone();
        local_paths.extend(realiased(&config.local_paths, &aliases));
        let mut local_programs = config.local_programs.clone();
        local_programs.extend(realiased(&config.local_programs, &aliases));
        Router {
            layouts,
            aliases,
            local_paths,
            local_programs,
            redirects,
            platform: OnceLock::new(),
            settled: OnceLock::new(),
        }
    }

    /// Records the platform the target said at the handshake (a Mac folds case). An empty
    /// answer is no answer; the first one given stands, a machine not becoming another one
    /// mid-session.
    pub fn learn_platform(&self, platform: &str) {
        if !platform.is_empty() {
            let _ = self.platform.set(platform.to_owned());
        }
    }

    /// What the target said it is, `""` before the handshake.
    pub fn platform(&self) -> &str {
        self.platform.get().map_or("", String::as_str)
    }

    /// Whether the target's filesystem ignores case, as a Mac's does by default. False
    /// before the handshake.
    pub fn insensitive(&self) -> bool {
        CASE_INSENSITIVE.contains(&self.platform())
    }

    /// The mirrors, longest root first.
    pub fn layouts(&self) -> &[Layout] {
        &self.layouts
    }

    /// The other names of the mirrors, normalised, as `(name, root)`.
    pub fn aliases(&self) -> &[(String, String)] {
        &self.aliases
    }

    /// The paths kept here, those named under an alias named again under its root.
    pub fn local_paths(&self) -> &[String] {
        &self.local_paths
    }

    /// The programs run here, those named under an alias named again under its root.
    pub fn local_programs(&self) -> &[String] {
        &self.local_programs
    }

    /// The redirects, normalised, longest named path first.
    pub fn redirects(&self) -> &[(String, String)] {
        &self.redirects
    }

    /// The one spelling of an absolute, normalised path that routing compares
    /// (`Router.canonical`).
    ///
    /// A path inside a layout -- named through `/private`, through an alias, or in whichever
    /// case a model typed for a target that ignores it -- is put back onto that layout's own
    /// root, the rest of it left exactly as it came. A path outside every layout comes back
    /// exactly as named. A session with nothing to settle answers without looking.
    pub fn canonical(&self, path: &str) -> String {
        if !self.settles() {
            return path.to_owned();
        }
        let insensitive = self.insensitive();
        let path = self.unaliased(path, insensitive);
        for layout in &self.layouts {
            if let Some(suffix) = layout.below(&path, insensitive) {
                let root = layout.local_root();
                return if suffix.is_empty() {
                    root.into_owned()
                } else {
                    join(&root, &suffix)
                };
            }
        }
        path
    }

    /// The path an alias names, put onto the root it is another name for.
    fn unaliased(&self, path: &str, insensitive: bool) -> String {
        for (name, root) in &self.aliases {
            if let Some(suffix) = path_within(path, name, insensitive) {
                return if suffix.is_empty() {
                    root.clone()
                } else {
                    join(root, &suffix)
                };
            }
        }
        path.to_owned()
    }

    /// Whether any path can need settling (so a session with none skips the work): the
    /// target folds case, there are aliases, or a mirror's root has a second spelling.
    /// Remembered only once the target has said what it is.
    pub fn settles(&self) -> bool {
        if let Some(settled) = self.settled.get() {
            return *settled;
        }
        let settles = self.insensitive()
            || !self.aliases.is_empty()
            || self
                .layouts
                .iter()
                .any(|one| spelled_twice(&one.local_root()));
        if self.platform.get().is_some() {
            let _ = self.settled.set(settles);
        }
        settles
    }

    /// The layout owning `path`, or `None` where it is this machine's (`Router.layout_for`).
    ///
    /// A path kept here is a hole only in the mirror it lies in, carved by the same rule the
    /// layout is matched by: a mirror kept inside a directory that stays here is the
    /// target's workspace all the same.
    pub fn layout_for(&self, path: &str) -> Option<&Layout> {
        let insensitive = self.insensitive();
        let layout = self
            .layouts
            .iter()
            .find(|one| one.contains(path, insensitive))?;
        let root = layout.local_root();
        let holed = self.local_paths.iter().any(|kept| {
            path_within(path, kept, insensitive).is_some()
                && path_within(kept, &root, insensitive).is_some_and(|below| !below.is_empty())
        });
        (!holed).then_some(layout)
    }

    /// Whether `path` is the target's.
    pub fn is_remote_path(&self, path: &str) -> bool {
        self.layout_for(path).is_some()
    }

    /// `path` as the target names it, or `None` where it is this machine's.
    pub fn to_virtual(&self, path: &str) -> Option<String> {
        self.layout_for(path)?.to_virtual(path)
    }

    /// A working directory as the target names it, a purely local one left untouched.
    pub fn virtual_cwd(&self, cwd: &str) -> String {
        self.to_virtual(cwd).unwrap_or_else(|| cwd.to_owned())
    }

    /// Where `path` is answered. The path is taken as given: a caller settles it with
    /// [`Router::canonical`] first.
    pub fn place(&self, path: &str) -> Place {
        match self.to_virtual(path) {
            Some(virtual_path) => Place::Mirror {
                local: PathBuf::from(path),
                virtual_path,
            },
            None => Place::Local,
        }
    }

    /// The path a `--redirect` answers `path` with, if any: by the entry that says most
    /// about it ([`policy::answered`]).
    pub fn swap(&self, path: &str) -> Option<String> {
        policy::answered(&self.redirects, path)
    }

    /// `text` with every mirror path rewritten to the target's (for argv and env sent there).
    ///
    /// A no-op where the mirror sits at the workspace's own path. Every name the mirror
    /// answers to is translated: each of its roots' spellings (`/private/tmp/m` for
    /// `/tmp/m`) and each alias naming exactly that root.
    pub fn rewrite(&self, text: &str) -> String {
        let insensitive = self.insensitive();
        let mut text = text.to_owned();
        for layout in &self.layouts {
            let root = layout.local_root();
            let target = layout.virtual_root();
            let named = self.aliases.iter().filter_map(|(name, aliased)| {
                (path_within(aliased, &root, insensitive).as_deref() == Some(""))
                    .then_some(name.as_str())
            });
            for one in std::iter::once(&*root).chain(named) {
                for spelling in path_spellings(one) {
                    text = rewrite_path_prefix(&text, &spelling, &target, insensitive);
                }
            }
        }
        text
    }

    /// Whether the program at `path` runs here rather than on the target: it lies under one
    /// of `local_programs`, compared as the target compares names.
    pub fn runs_locally(&self, path: &str) -> bool {
        let insensitive = self.insensitive();
        self.local_programs
            .iter()
            .any(|prefix| path_within(path, prefix, insensitive).is_some())
    }
}

/// Each of `paths` under an alias, named again under the root it is another name for
/// (`Router._realiased`). Compared exactly: the platform is not known yet.
fn realiased(paths: &[String], aliases: &[(String, String)]) -> Vec<String> {
    paths
        .iter()
        .flat_map(|kept| {
            aliases.iter().filter_map(move |(name, root)| {
                path_within(kept, name, false).map(|suffix| {
                    if suffix.is_empty() {
                        root.clone()
                    } else {
                        join(root, &suffix)
                    }
                })
            })
        })
        .collect()
}

/// `os.path.abspath(os.path.expanduser(path))` without a trailing slash (`policy._normalise`).
fn normalise(path: &str) -> String {
    let expanded = abspath(&expanduser(path));
    let trimmed = expanded.trim_end_matches('/');
    if trimmed.is_empty() {
        "/".to_owned()
    } else {
        trimmed.to_owned()
    }
}
