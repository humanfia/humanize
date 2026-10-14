# Changelog

## [0.2.0-beta.3](https://github.com/humanfia/humanize/compare/v0.2.0-beta.2...v0.2.0-beta.3) (2026-10-14)


### ⚠ BREAKING CHANGES

* **runtime:** runtimes take `harness` instead of `affinity`, and work on another machine with no setting no longer drops to a harness here when the CLI is missing or a gating hook is hung: set the runtime's harness to `local`. A saved `affinity` is still read, as its first entry with `self` as `env`.

### Features

* chat like Claude, no all-sessions log, Exomyth fixes, split profiling, TUI parity ([#422](https://github.com/humanfia/humanize/issues/422)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* many chats, each its own epic beside the workspace's flow, folding away when idle ([#427](https://github.com/humanfia/humanize/issues/427)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* rewrite specs as api/ and features/, pick the btw agent per epic, refuse cross-machine workspace hooks ([#444](https://github.com/humanfia/humanize/issues/444)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **runtime:** let docker and swarm runtimes share a host: name prefix, exec user, running container ([#426](https://github.com/humanfia/humanize/issues/426)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **runtime:** say where a harness runs with one setting, not four placements ([#446](https://github.com/humanfia/humanize/issues/446)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))


### Fixes

* **agents:** retry Codex's dropped streams and start every harness in a virtual config home ([#425](https://github.com/humanfia/humanize/issues/425)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **coganchor:** build a harness's virtual home on its own machine under afar ([#445](https://github.com/humanfia/humanize/issues/445)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **coganchor:** keep the turns of the shared-mirror test in the mirror at once ([#442](https://github.com/humanfia/humanize/issues/442)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **coganchor:** let turns working in one mirror at once see each other's work ([#423](https://github.com/humanfia/humanize/issues/423)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **flows:** keep and carry on supervised sessions, whose CLI runs here in a mirror ([#424](https://github.com/humanfia/humanize/issues/424)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **telemetry:** scrub reports as bundles are, timings and profiles too, only where started ([#439](https://github.com/humanfia/humanize/issues/439)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))
* **tui,web:** call an execution of a flow an epic in every label and message ([#447](https://github.com/humanfia/humanize/issues/447)) ([33ed4dd](https://github.com/humanfia/humanize/commit/33ed4ddc357394bba9311ace5e61d9f24a389e4e))

## [0.2.0-beta.2](https://github.com/humanfia/humanize/compare/v0.2.0-beta.1...v0.2.0-beta.2) (2026-10-13)


### Features

* call every agent by its own name, never by the role it fills ([#401](https://github.com/humanfia/humanize/issues/401)) ([2b0148a](https://github.com/humanfia/humanize/commit/2b0148a9868be32774c0a25015741eec25143542))
* **desktop:** lay out the disk image with first-open steps, and line up the web's controls ([#396](https://github.com/humanfia/humanize/issues/396)) ([3c2689e](https://github.com/humanfia/humanize/commit/3c2689e68d7ae181cd7abfb3b753ab31c4c5f298))
* **web:** keep only Daemon, Settings and Usage in the sidebar's foot menu ([#394](https://github.com/humanfia/humanize/issues/394)) ([43e614c](https://github.com/humanfia/humanize/commit/43e614c716452b28fdb9ece106433835ab7d9368))


### Fixes

* **desktop:** keep a strip for the traffic lights over the sidebar's top row ([#402](https://github.com/humanfia/humanize/issues/402)) ([2b0148a](https://github.com/humanfia/humanize/commit/2b0148a9868be32774c0a25015741eec25143542))
* **desktop:** keep the traffic lights' strip across the whole window ([#403](https://github.com/humanfia/humanize/issues/403)) ([2b0148a](https://github.com/humanfia/humanize/commit/2b0148a9868be32774c0a25015741eec25143542))
* line up the sidebar's top row with the traffic lights, and every row on one column ([#399](https://github.com/humanfia/humanize/issues/399)) ([2b0148a](https://github.com/humanfia/humanize/commit/2b0148a9868be32774c0a25015741eec25143542))

## 0.2.0-beta.1 (2026-10-13)


### ⚠ BREAKING CHANGES

* **web:** hmz web no longer serves only the directory it was started in, and every request about one workspace's runs names it; GET /api/held answers the machine's context.
* **web:** the page's addresses move: #/runs/<name> is #/epics/<name>, #/start is #/new, #/runs?… is #/search?… and #/usage is #/settings/usage.
* **flows:** ralph_loop and continue_loop are no longer resumable. stateful_ralph now keeps its session in state, so --resume carries the conversation on. flame_chase keeps only whose turn is next, and rlar keeps only the last review. A failed turn now ends any of these runs.

### Features

* **agents:** drive omp (Oh My Pi) as a backend ([#283](https://github.com/humanfia/humanize/issues/283)) ([5a7ac5a](https://github.com/humanfia/humanize/commit/5a7ac5a9ebdfba37c5a81e88ce31a904449d3c8e)), refs [#280](https://github.com/humanfia/humanize/issues/280)
* **agents:** offer a flow's callback tools to ACP CLIs and grok over mcpServers ([#338](https://github.com/humanfia/humanize/issues/338)) ([3bf9af0](https://github.com/humanfia/humanize/commit/3bf9af0a8ad27d60b1c61a89a26c8ad146e007f6))
* **agents:** offer a flow's callbacks to Antigravity CLI as a plugin ([#339](https://github.com/humanfia/humanize/issues/339)) ([c9eed02](https://github.com/humanfia/humanize/commit/c9eed021dfdc9bac7ceae0aff1d236586dcd7578))
* **agents:** offer a flow's callbacks to opencode and mimocode ([#336](https://github.com/humanfia/humanize/issues/336)) ([127ac9c](https://github.com/humanfia/humanize/commit/127ac9cdd831221f7dc9530b86b0bdcb147d1e7f))
* **agents:** offer a flow's callbacks to pi, Oh My Pi and DeepSeek Harness ([#341](https://github.com/humanfia/humanize/issues/341)) ([6bbf96b](https://github.com/humanfia/humanize/commit/6bbf96ba0574a4d00eb0e3a4607d2eab67fd1963))
* **agents:** offer a flow's own callbacks to Qwen Code ([#337](https://github.com/humanfia/humanize/issues/337)) ([2ac6d3e](https://github.com/humanfia/humanize/commit/2ac6d3e766b14adeaf4977ecda76ce5c1fe8beb6))
* **agents:** put a flow's own command lines on an agent's PATH ([#342](https://github.com/humanfia/humanize/issues/342)) ([46e38c6](https://github.com/humanfia/humanize/commit/46e38c6c2520b505dbf55cd6464af895bba5cfec))
* **cli:** update hmz itself with hmz update, and say when a newer release is out ([#318](https://github.com/humanfia/humanize/issues/318)) ([7854f0a](https://github.com/humanfia/humanize/commit/7854f0af92d9f2399878b83e1c56223541170e89))
* **coganchor:** route any CLI through a local LiteLLM gateway ([#343](https://github.com/humanfia/humanize/issues/343)) ([1d49b9e](https://github.com/humanfia/humanize/commit/1d49b9e8799706b2a6e1d3c5ebe8a0c6fd53ec31))
* **daemon:** let a line said to a conversation between turns answer what to say next ([#333](https://github.com/humanfia/humanize/issues/333)) ([7d89b54](https://github.com/humanfia/humanize/commit/7d89b549246e5b00175d135f6dc186ee3f1b0301))
* **desktop:** a macOS app around hmz web, shipped as a DMG on every release ([#310](https://github.com/humanfia/humanize/issues/310)) ([02b60eb](https://github.com/humanfia/humanize/commit/02b60ebe8abb1ebe7abf2d4910129c04132d23b6))
* **desktop:** install and keep hmz at the app's own version, by itself ([#316](https://github.com/humanfia/humanize/issues/316)) ([be44c6b](https://github.com/humanfia/humanize/commit/be44c6b79c181666009e45e0b5e2a582648a5ef6))
* **desktop:** make the title bar one with the page ([#314](https://github.com/humanfia/humanize/issues/314)) ([a77103a](https://github.com/humanfia/humanize/commit/a77103a17c6f523c010f29ead4efb4cbca4a0e20))
* **desktop:** open .hmzepic files, importing them into Exomyth ([#365](https://github.com/humanfia/humanize/issues/365)) ([ad0827d](https://github.com/humanfia/humanize/commit/ad0827dbb7f54d713add4b904f4c97aa843a1f45))
* **desktop:** update the app by itself, signed, from each release ([#315](https://github.com/humanfia/humanize/issues/315)) ([d1f2d18](https://github.com/humanfia/humanize/commit/d1f2d18c5b10196897324f46165d3d377e2d050f))
* **flows:** carry a session kept in a flow's state on in a later run ([#172](https://github.com/humanfia/humanize/issues/172)) ([896a089](https://github.com/humanfia/humanize/commit/896a0894c1f078742146241d72426349c35e3586))
* **flows:** offer a role's FakeTools to its agent as tools of the flow's own ([#340](https://github.com/humanfia/humanize/issues/340)) ([4de535d](https://github.com/humanfia/humanize/commit/4de535d48746c92c4222777108c5480254179808))
* **flows:** one FakeTool, FakeCli and FakeCommand for flows and coganchor ([#364](https://github.com/humanfia/humanize/issues/364)) ([af428c2](https://github.com/humanfia/humanize/commit/af428c2809d11f23ca74489f8afb6049c526b737))
* land the open web and LiteLLM gateway pull requests together ([#367](https://github.com/humanfia/humanize/issues/367)) ([d7f732e](https://github.com/humanfia/humanize/commit/d7f732e935100047d0faa5fc7c4d6b03ce350fc7))
* many daemons in web and desktop, and notifications across them ([#385](https://github.com/humanfia/humanize/issues/385)) ([6514f96](https://github.com/humanfia/humanize/commit/6514f96acd3421ad67f63e4d138287ebdc618b0e))
* **runtime:** back epics up to git repositories ([#331](https://github.com/humanfia/humanize/issues/331)) ([0beb7cf](https://github.com/humanfia/humanize/commit/0beb7cf1dd4471bf7f7cc838708591badbd6ebf0))
* **runtime:** download epics from backup targets ([#355](https://github.com/humanfia/humanize/issues/355)) ([bab4db1](https://github.com/humanfia/humanize/commit/bab4db16880d64190e86b374068752205d4625e7))
* **runtime:** export epics as .hmzepic and import them back ([#327](https://github.com/humanfia/humanize/issues/327)) ([f12acb0](https://github.com/humanfia/humanize/commit/f12acb01f90f1b4fc30db96c94229c9714078780))
* **runtime:** lay an epic out as an Exomyth timeline ([#326](https://github.com/humanfia/humanize/issues/326)) ([09d0192](https://github.com/humanfia/humanize/commit/09d0192b0eaeb187ef766fbde4c5fe010804306e))
* **runtime:** put environments on Slurm jobs, reached by srun or over TCP ([#317](https://github.com/humanfia/humanize/issues/317)) ([32b0e45](https://github.com/humanfia/humanize/commit/32b0e45645db1669c1f5728dd90829124069a4dd))
* **tui:** add Exomyth, a timeline of an epic's sessions ([#345](https://github.com/humanfia/humanize/issues/345)) ([6d0e67f](https://github.com/humanfia/humanize/commit/6d0e67f4f42c5773bf33cb597c3c5a6e9aed5ce8))
* **tui:** answer chat's questions in the conversation being read ([#334](https://github.com/humanfia/humanize/issues/334)) ([046f562](https://github.com/humanfia/humanize/commit/046f5621366986737cf5bc87766942c9e7e62fca))
* **tui:** back epics up from /settings, /flow and /epics ([#352](https://github.com/humanfia/humanize/issues/352)) ([14de0fa](https://github.com/humanfia/humanize/commit/14de0fa95945db788d5b9845612fae21a02b38e3))
* **tui:** import an epic from a .hmzepic ([#354](https://github.com/humanfia/humanize/issues/354)) ([9f1f931](https://github.com/humanfia/humanize/commit/9f1f9315c65105d575b4ad964fd4fde4cf37f7fe))
* **tui:** show the epics of this directory or of this machine ([#325](https://github.com/humanfia/humanize/issues/325)) ([194a061](https://github.com/humanfia/humanize/commit/194a0611cd2f8c38e01e74011e232a4a0d4c1df1))
* **web:** add Exomyth, a timeline of an epic's sessions ([#344](https://github.com/humanfia/humanize/issues/344)) ([d12da19](https://github.com/humanfia/humanize/commit/d12da19adc5fce5c67ef3eb1be256c4fdf66ebc5))
* **web:** ask a session of any epic beside it, and read epics back out of their logs ([#305](https://github.com/humanfia/humanize/issues/305)) ([2363cb9](https://github.com/humanfia/humanize/commit/2363cb9ac839bdd2240859ac7c8c2eb64f520b0b))
* **web:** back epics up from Settings, launch and the epic menu ([#351](https://github.com/humanfia/humanize/issues/351)) ([cebac23](https://github.com/humanfia/humanize/commit/cebac238a5e7f9b0726b17e71af504214a85710e))
* **web:** choose a theme only in Settings ([#323](https://github.com/humanfia/humanize/issues/323)) ([3c61e7e](https://github.com/humanfia/humanize/commit/3c61e7e895ca282f5a13bb9d403edac4a7aac8da))
* **web:** come with a light and a dark theme for every Chrysos Heir, and pair them under Auto ([#321](https://github.com/humanfia/humanize/issues/321)) ([f9ff098](https://github.com/humanfia/humanize/commit/f9ff098a544082e7d7e8b5fd92871eeaebeaa656))
* **web:** do what the terminal interface does to flows and epics ([#304](https://github.com/humanfia/humanize/issues/304)) ([e16e329](https://github.com/humanfia/humanize/commit/e16e329ac274a7d7d08b0c75f1220e4422d69683))
* **web:** draw an epic's Exomyth as a flame graph, with its slices in a table ([#363](https://github.com/humanfia/humanize/issues/363)) ([14929ec](https://github.com/humanfia/humanize/commit/14929ecf0b6e56c0754e63638c531ec87552bd31))
* **web:** draw humanize in NVIDIA's green and Hyacine's colours ([#302](https://github.com/humanfia/humanize/issues/302)) ([d0731e4](https://github.com/humanfia/humanize/commit/d0731e44565044946b1b6f61c72d375984a028ea))
* **web:** hmz web serves a workspace's runs to a browser on this machine ([#285](https://github.com/humanfia/humanize/issues/285)) ([cae5859](https://github.com/humanfia/humanize/commit/cae58590771d65a4baf04bcac460ed3275cd709c))
* **web:** import an epic from a .hmzepic ([#356](https://github.com/humanfia/humanize/issues/356)) ([9437fe0](https://github.com/humanfia/humanize/commit/9437fe026acbf890740687c90b1bd43717b5cbf5))
* **web:** lay hmz web out as Codex and Claude lay theirs out ([#300](https://github.com/humanfia/humanize/issues/300)) ([21a1379](https://github.com/humanfia/humanize/commit/21a1379342faebad8bfc9ca6bb0a5a9d5327ccc2))
* **web:** make a light and a dark theme a pair of your own, written out together ([#328](https://github.com/humanfia/humanize/issues/328)) ([af884d4](https://github.com/humanfia/humanize/commit/af884d4d5929128b8ce81d295dcd9a0e510f096e))
* **web:** make, edit, import and export themes, and pair any two under Auto ([#320](https://github.com/humanfia/humanize/issues/320)) ([02dbd5e](https://github.com/humanfia/humanize/commit/02dbd5e3eee4fd306a76f07e17a596ce99b6a8ee))
* **web:** open a chat on its conversation, and ask in it ([#335](https://github.com/humanfia/humanize/issues/335)) ([c113c55](https://github.com/humanfia/humanize/commit/c113c5587617deca249974f65c052361af35fca8))
* **web:** redesign in NVIDIA's green beside Hyacine's cyan, and her pink apart ([#307](https://github.com/humanfia/humanize/issues/307)) ([f71dea2](https://github.com/humanfia/humanize/commit/f71dea2b358dcfa24e22652bd319429eac4aa9f6))
* **web:** right-click menus, full text on hover, and paths browsed for rather than typed ([#313](https://github.com/humanfia/humanize/issues/313)) ([475b6f6](https://github.com/humanfia/humanize/commit/475b6f6fbc85b574ceb8b0ffc05d129d323abc1f))
* **web:** serve every workspace on the machine, as the daemon does ([#303](https://github.com/humanfia/humanize/issues/303)) ([ef0e9e5](https://github.com/humanfia/humanize/commit/ef0e9e59785d7d0d0be6dc4c00af41f6208db445))
* **web:** stop hmz web when whatever started it goes ([#306](https://github.com/humanfia/humanize/issues/306)) ([7997c21](https://github.com/humanfia/humanize/commit/7997c218999bd956eaa1237754367dd5ef847673))


### Fixes

* **agents:** let fenced Codex initialize TLS on macOS and fail turns that end in error ([#281](https://github.com/humanfia/humanize/issues/281)) ([15e9995](https://github.com/humanfia/humanize/commit/15e99952c7106d9a7be25921f3e8c58dd7fa6683))
* **agents:** prefix pi and omp flow tools, let omp take them remotely ([#361](https://github.com/humanfia/humanize/issues/361)) ([3964e98](https://github.com/humanfia/humanize/commit/3964e98d3279b6133a846055108e7297f8f02ff5))
* **agents:** refuse a dsh turn that would need a new runtime for a conversation ([#362](https://github.com/humanfia/humanize/issues/362)) ([8b1c073](https://github.com/humanfia/humanize/commit/8b1c07370d84197ca0ee22c1fb284e14f49104e8))
* **anchor:** copy sessions a CLI logs on another machine into the epic ([#324](https://github.com/humanfia/humanize/issues/324)) ([069c3fe](https://github.com/humanfia/humanize/commit/069c3fe3ac0ae0168d161c20fe6d5780acb96267))
* **coganchor:** let a fence write /proc, and let local and user of ALL write what they say ([#278](https://github.com/humanfia/humanize/issues/278)) ([60cab7e](https://github.com/humanfia/humanize/commit/60cab7e69fbff07dd2968088df6a64c6e23accd6))
* **coganchor:** let a fence write /proc, and let local and user of ALL write what they say ([#287](https://github.com/humanfia/humanize/issues/287)) ([60cab7e](https://github.com/humanfia/humanize/commit/60cab7e69fbff07dd2968088df6a64c6e23accd6))
* **flows:** drop the trailing comma CodeQL cannot parse in type parameter lists ([#293](https://github.com/humanfia/humanize/issues/293)) ([5d0fe0b](https://github.com/humanfia/humanize/commit/5d0fe0b42485973d528d51c8b49bcf005bb8effb))
* **flows:** let rlar's reviewer read what the actor said ([#290](https://github.com/humanfia/humanize/issues/290)) ([a8651f1](https://github.com/humanfia/humanize/commit/a8651f1124cb9145054d550bb25ce8ac67412802))
* list a run hmz exec holds as going in hmz web and /epics ([#370](https://github.com/humanfia/humanize/issues/370)) ([085fd0a](https://github.com/humanfia/humanize/commit/085fd0a72785e566a65a0b56d11e674b9eb5d2f6))
* order epics begun in one millisecond, and keep a left view out of the next one's address ([#360](https://github.com/humanfia/humanize/issues/360)) ([18cd580](https://github.com/humanfia/humanize/commit/18cd5801aed2b293a48b37d79b0f40b0e8e871d7))
* **web:** draw the view an address names, never one left or one under a dialog ([#357](https://github.com/humanfia/humanize/issues/357)) ([45184e7](https://github.com/humanfia/humanize/commit/45184e7bdc3cc299a121c76f896bd1cf49eba624))
* **web:** keep long flow and workspace names inside what shows them ([#329](https://github.com/humanfia/humanize/issues/329)) ([1e765bc](https://github.com/humanfia/humanize/commit/1e765bc170b3c12462f35271e22b89897e1030b4))
* **web:** pick an agent and an environment a step at a time, and test the page in a browser ([#301](https://github.com/humanfia/humanize/issues/301)) ([27dfb41](https://github.com/humanfia/humanize/commit/27dfb418e5e4766c34811b646fecb5a2486c926c))
* **web:** say what an epic's environments are, and fit its spending in the panel ([#309](https://github.com/humanfia/humanize/issues/309)) ([cc17577](https://github.com/humanfia/humanize/commit/cc175771c4511b7c3761087b08c1fe9d0f8d716d))


### Refactoring

* **flows:** strip the builtin loops to their purest form ([#298](https://github.com/humanfia/humanize/issues/298)) ([f855a01](https://github.com/humanfia/humanize/commit/f855a017faf8282d1627f2fbd712abac37d7628b))
