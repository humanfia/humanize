# Git Worktree 子进程并行隔离实施计划

## 目标说明

以尽可能小的 Humanize 核心改动，为并行 writer job 提供 Git worktree 隔离。隔离单位不再是
进程内的单个 Agent，而是一次完整的 writer job：每个 job 获得一个从共同 `base_sha` 创建的
独立 worktree，并由父协调器以该 worktree 为 `cwd` 启动一个现有命令，通常是完整的
`hmz exec ...` argv。job 内可以运行单 Agent flow，也可以运行共享同一工作区的
actor/reviewer 多 Agent flow。

本计划采用以下固定边界：

- 一个 writer job 对应一个不可变的 worktree 路径和一个独立子进程。
- 所有 writer worktree 从同一个固定 `base_sha` 以 detached HEAD 创建，不创建临时 writer
  branch 或 integration branch。
- 父协调器不调用 `os.chdir()`；Git 命令、writer 子进程和集成检查都使用显式 `cwd`。
- writer 只负责运行 flow、修改文件和执行它认为需要的局部检查，不负责提供最终提交契约。
- writer 退出后，协调器根据 worktree 的实际 Git 状态统一 squash 并创建至多一个结果提交；
  没有变化是合法的 `no_change` 结果。
- 只有全部 writer 成功后，才在独立 integration worktree 中按输入顺序 cherry-pick，并运行
  调用方给定的检查命令。
- 发布前主工作区和 target branch 保持在启动时状态；发布使用主工作区中的
  `git merge --ff-only <integration_tip>`。
- 完全成功后清理 managed worktree；writer、集成、检查或发布失败时保留现场。
- 第一版只提供 Python 侧显式入口，不改变 `Runner.run()`、现有 `hmz exec` 语法和普通 flow
  行为，也不修改任何 Agent、app-server、machine 或 provider 实现。
- 这是协作式文件隔离，不是安全边界。子进程和 worktree 仍共享主机资源、Git object
  database、refs、用户凭据和网络。

理想执行顺序如下：

```text
clean repository -> 固定 repo_root、target_branch 和 base_sha
                 -> 串行创建 N 个 detached writer worktree
                 -> 有界并行启动 N 个子进程，每个 cwd 指向自己的 worktree
                 -> 等待全部 writer 结束
                 -> 协调器在各 worktree 中统一生成 result commit 或 no_change
                 -> 创建 detached integration worktree
                 -> 按 job 输入顺序 cherry-pick result commits
                 -> 运行集成检查并确认 integration worktree clean
                 -> 再次确认主工作区和 target branch 未移动
                 -> 从主工作区 fast-forward 到 integration tip
                 -> 验证发布结果，再清理成功 worktree
```

## Python 入口契约

第一版在 `hmz.runner` 中提供独立于 `Runner.run()` 的显式入口。具体命名可以遵循实现时
的代码风格，但契约应等价于：

```python
@dataclass(frozen=True, slots=True)
class WorktreeJob:
    name: str
    argv: tuple[str, ...]


def run_worktrees(
    jobs: Sequence[WorktreeJob],
    *,
    checks: Sequence[Sequence[str]] = (),
    at_once: int = 0,
) -> WorktreeRunResult: ...
```

- `argv` 是不经过 shell 的完整命令，常见值为 `("hmz", "exec", ...)` 或
  `(sys.executable, "-m", "hmz", "exec", ...)`。协调器不重新解析或重建 Agent 配置。
- `at_once=0` 表示同时运行全部 job；正整数限制并发子进程数。
- `checks` 是按顺序执行的 argv 列表，全部在 integration worktree 中运行。
- job 名必须非空且在本次 run 中唯一；worktree 路径仍以稳定序号生成，不直接依赖 job 名。
- 预检或参数错误在创建任何 worktree 前抛出；一旦首个 lease 创建成功，后续创建、writer、
  集成、检查和发布失败都以结构化失败结果返回，并包含所有保留路径。
- 结果只记录可观测事实，不复制 Agent 自然语言输出。run 级字段至少包含 `status`、
  `repo_root`、`target_branch`、`base_sha`、`published_sha`、job 结果、检查结果、保留路径和
  cleanup errors。job 级字段至少包含 `name`、`returncode`、`source_commit`、
  `integrated_commit`、`changed_paths`、`status`、`worktree_path` 和错误信息。
- 第一版不持久化额外 JSON。成功结果由已发布 target branch 持久化；失败现场由保留的
  worktree 和 Git 元数据持久化。结构化结果由 Python 调用方决定是否另行保存。

## 验收标准

遵循 TDD，下面每项均包含可确定执行的正向和反向测试。

- AC-1：协调器在启动任何子进程前完成输入和 repository 预检。
  - 正向测试（预期通过）：
    - 在临时 clean Git repository 中解析绝对 `repo_root`、当前非 detached target branch 和
      `base_sha`，且整个 run 始终使用这些冻结值。
    - 接受一个或多个唯一、非空名称且 argv 非空的 job；接受空 checks 和 argv 形式 checks。
    - `at_once=0` 或正整数均被接受。
  - 反向测试（预期被拒绝且不创建 worktree）：
    - 当前目录不在 Git worktree 中、Git 不可执行、当前 HEAD detached，或 HEAD 无法解析。
    - repository 存在 staged、unstaged 或 untracked 变更。
    - jobs 为空、名称为空或重复、argv 为空、check argv 为空，或 `at_once` 为负数。
    - 生成的 managed 路径经真实路径校验后位于 repository root 内。

- AC-2：每个 writer job 在独立 worktree 的子进程中运行。
  - 正向测试（预期通过）：
    - 为两个 job 串行执行 `git worktree add --detach <path> <base_sha>`；两个 worktree 的初始
      HEAD 均为同一 `base_sha`，但绝对路径、working tree、index 和 worktree HEAD 各自独立。
    - 父协调器以显式 `cwd=<writer_path>` 启动完整 argv，不改变父进程 cwd；fake writer
      观察到的进程 cwd 正是分配路径。
    - 两个 fake writer 并行修改同一个相对路径为不同内容，各自始终只能读到自己的内容，
      主工作区保持基线内容。
    - 一个 job 中运行的现有 `hmz exec` 可以继续驱动一个或多个 Agent；该子进程的所有普通
      backend、长期 app-server、workspace metadata 和项目 skills 继续使用现有 cwd 语义。
    - 并发 job 数从未超过 `at_once`，结果顺序保持为输入顺序而非完成顺序。
  - 反向测试（预期失败并保留现场）：
    - 任一 worktree 创建失败，或子进程无法启动、非零退出、被信号终止。
    - 一个 writer 失败时不启动 integration，也不发布其他成功 writer 的部分结果；已经启动
      的 writer 会被等待到结束，避免把仍在运行的进程遗留给下一阶段。
    - 协调器被中断时终止并等待仍在运行的直属 writer 子进程，不进行 Git 收尾或发布，并
      保留已经创建的 worktree。

- AC-3：最终 writer 提交完全由协调器根据 Git 状态生成。
  - 正向测试（预期通过）：
    - writer 留下 staged、unstaged、untracked、删除或重命名改动时，协调器使用
      `git add -A` 捕获最终 snapshot，并创建一个以 `base_sha` 为唯一 parent 的结果提交。
    - writer 自己产生一个或多个提交时，只要 detached HEAD 仍是 `base_sha` 的后代且没有
      未解决的 Git 操作，协调器使用 `git reset --soft <base_sha>` 合并已有提交和未提交改动，
      再生成恰好一个结果提交。
    - writer 最终 snapshot 与基线相同时返回 `no_change`，不制造空提交；integration 阶段跳过
      该 job，但仍保留其成功结果。
    - `changed_paths` 通过 `git diff --name-only -z <base_sha> <result_commit>` 获得；完成后
      writer worktree 对非 ignored 文件为 clean。
    - 协调器提交使用仅限当前 Git 命令的固定 identity，并关闭 commit signing，不读取或修改
      repository/global Git 配置中的用户身份。
  - 反向测试（预期失败并保留现场）：
    - writer 切换到 named branch、HEAD 不是 `base_sha` 的后代、留下 unmerged entries，或
      正处于 merge、rebase、cherry-pick 等未完成 Git 操作。
    - `git add`、commit、changed-path 查询或 clean 验证失败。
    - 失败不能被 Agent 的成功退出码或自然语言完成声明覆盖。

- AC-4：成功 writer 在独立 integration worktree 中按稳定顺序集成并验证。
  - 正向测试（预期通过）：
    - integration worktree 同样以 detached HEAD 从 `base_sha` 创建，并按 job 输入顺序对所有
      非 `no_change` 的 `source_commit` 执行 `git cherry-pick`。
    - 每次 cherry-pick 后记录新的 integration HEAD 为该 job 的 `integrated_commit`，避免清理
      writer worktree 后只留下可能被 Git GC 的 source commit。
    - cherry-pick 与 writer commit 一样使用仅限当前命令的固定 committer identity，并关闭
      commit signing，不修改 repository 或 global Git 配置。
    - 调用方给定的检查命令按顺序、以 argv 形式和 `cwd=integration_path` 执行；全部返回零后
      才允许发布。
    - 检查完成后再次验证 integration worktree 对非 ignored 文件 clean，确保发布的 tree 与
      实际通过检查的 tree 相同。
    - 全部 job 都是 `no_change` 时仍从基线运行检查，成功后返回 unchanged，而不创建提交。
  - 反向测试（预期失败并保留现场）：
    - 任一 cherry-pick 冲突时立即停止，不继续后续提交、不运行 checks、不发布，也不自动
      `cherry-pick --abort`。
    - 任一 check 非零退出、无法启动，或 check 留下 tracked/untracked 非 ignored 改动时不发布。

- AC-5：发布只在主工作区仍精确处于启动状态时发生。
  - 正向测试（预期通过）：
    - 发布前重新确认主工作区仍 checkout 原 `target_branch`、`HEAD == base_sha`、target ref 指向
      `base_sha`，并且 `git status --porcelain=v1 --untracked-files=all` 为空。
    - 从主工作区执行 `git merge --ff-only <integration_tip>`；成功后 target branch 和主工作区
      同步前进到 integration tip。
    - 发布后再次验证 `HEAD == integration_tip`、主工作区 clean，且 tree 与 integration tree
      相同，随后才把 run 标为 published。
  - 反向测试（预期失败并保留现场）：
    - 启动后 target branch 或 HEAD 移动、主工作区切换 branch 或变脏、fast-forward 失败，或
      发布后验证不一致。
    - 失败时不尝试 reset、rebase、force-update 或回滚调用方的并发修改。

- AC-6：成功清理只操作精确 managed 路径，任何业务失败都保留诊断现场。
  - 正向测试（预期通过）：
    - 完全发布或 unchanged 且检查通过后，逐个验证 worktree 仍属于本次 run、HEAD 符合记录、
      非 ignored 文件 clean，再调用 `git worktree remove --force <exact_path>`。`--force` 只用于
      清除测试工具产生的 ignored 构建环境和缓存，不用于跳过 tracked 改动验证。
    - detached worktree 清理后无需删除任何 branch；主 target branch 保留正式结果。
    - 清理失败不改变已经成功的 published/unchanged 业务状态，结果中记录 cleanup error 和
      残留路径。
  - 反向测试（预期通过其保护行为）：
    - writer、集成、检查、发布或中断失败时不删除任何已经创建的 writer/integration worktree。
    - 待删除路径不属于当前 run、解析后越出 managed run directory，或 HEAD/status 与记录不符
      时拒绝清理。
    - 不直接递归删除 worktree 目录，也不调用 `git worktree prune` 影响其他 run。

- AC-7：改动不影响当前 Agent、flow、CLI 和 package layering。
  - 正向测试（预期通过）：
    - 现有同步/异步 flow、同 workspace actor/reviewer、Agent `batch()`/`abatch()`、anchored
      machine、provider、Codex/Kimi app-server 测试保持通过。
    - 普通 `Runner.run()` 和 `hmz exec` 继续在调用进程当前目录运行，不自动创建 worktree。
    - 新测试只使用 fake argv 和临时 Git repository，不调用真实 Claude、Codex 或 Kimi 服务。
    - `uv run pre-commit run --all-files` 和 `uv run pytest` 均通过。
    - diff 不包含任何 `SPEC.md`、README、CLI、AgentConfig 或无关重构。
  - 反向测试（预期被拒绝）：
    - 实现修改 `agents/base.py`、`agents/codex.py`、`agents/kimi.py` 的 cwd 行为，依赖全局
      `os.chdir()`，或新增顶层 package layer。
    - 实现从 Agent 文本输出推断 changed paths、测试结果或提交状态。

## 路径边界

### 上界（最大可接受范围）

- 在 `runner.py` 中增加一个独立于 `Runner.run()` 的小型 Python 协调入口，以及必要的 job、
  lease、check 和 result 数据类型。
- 完整覆盖 clean preflight、detached worktree 创建、并发子进程管理、协调器提交、顺序集成、
  argv checks、发布竞争检查、fast-forward 发布、成功清理和失败保留。
- 支持任意数量的 writer job；一个 job 的 argv 可以运行任意现有单 Agent 或多 Agent flow。
- 对创建、提交、集成、冲突、no-change、并发上限、发布竞争、中断和清理进行确定性测试。

### 下界（最小可接受范围）

- 至少两个现有命令能在共同基线的不同 detached worktree 中并行运行，父进程和主工作区 cwd
  均不改变。
- 协调器能把每个成功 writer 的最终 snapshot 规范化为至多一个提交，并支持 no-change。
- 能在 detached integration worktree 中顺序 cherry-pick、运行检查并安全 fast-forward 发布。
- 任何业务失败都不修改 target branch，并保留可诊断 worktree；完全成功后可清理。
- 不修改 Agent、app-server、machine、provider、CLI、README 或任何 SPEC。

### 允许的选择

- 可以使用：
  - Python 标准库的 `subprocess`、`pathlib`、`dataclasses`、`concurrent.futures`、`threading`、
    `uuid` 和现有 `hmz.home()`。
  - 系统 Git CLI；所有命令使用 argv list、显式 `cwd`、捕获必要的 stdout/stderr，不使用 shell。
  - `git worktree add --detach`、`git status --porcelain`、`git symbolic-ref`、
    `git merge-base --is-ancestor`、`git reset --soft`、`git add -A`、
    `git diff --name-only -z`、`git cherry-pick`、`git merge --ff-only` 和
    `git worktree remove --force` 等稳定 Git 接口。
  - `HUMANIZE_HOME/worktrees/<run-id>/writer-<index>` 和 `integration` 作为 managed 路径；run id
    使用随机 UUID，序号提供稳定顺序。
- 不可以使用：
  - Agent workspace 绑定、修改 `AgentConfig`、修改 backend `Popen`、进程级 `os.chdir()`。
  - 新 CLI 命令或参数、shell 字符串、`shell=True`、临时 Git branch、stash、自动 rebase 或
    语义自动合并。
  - 解析 Agent 自然语言结果来判断成功、changed paths、tests 或 risks。
  - 自动 `cherry-pick --abort`、`reset --hard` 主工作区、force-update target branch、直接递归
    删除 worktree，或清理不属于当前 run 的路径。
  - 第一版中的 JSON manifest、crash resume、长期 GC、跨 repository job、submodule/LFS 编排、
    dirty tree snapshot、remote/container writer 或安全沙盒承诺。

## 可行实现路径

### 1. 冻结 repository 状态

在创建任何目录前，以调用进程当前目录为起点执行：

```text
repo_root      = git rev-parse --show-toplevel
target_branch  = git symbolic-ref --quiet --short HEAD
base_sha       = git rev-parse HEAD
clean          = git status --porcelain=v1 --untracked-files=all 输出为空
```

把 `repo_root` 和 managed root 分别做真实路径比较，只把解析后的路径用于边界验证；传给子进程
和结果的路径使用创建 worktree 时确定的绝对路径。拒绝 managed root 位于 repository 内的配置。

### 2. 创建 lease 并启动 writer

先串行创建全部 writer lease：

```text
git worktree add --detach <writer_path> <base_sha>
```

随后按 `at_once` 有界并行启动：

```text
Popen(job.argv, cwd=writer_path)
```

不改写 argv、不调用 shell、不创建 Agent 对象。子进程继承调用方环境和标准流，因此现有
`hmz exec` 的 provider、hooks、Cycle、输出和信号行为不需要在协调器中复制。父协调器登记每个
`Popen`，正常路径等待全部 writer；中断路径终止并等待仍在运行的直属子进程。

### 3. 规范化 writer snapshot

只对退出码为零的 writer 执行 Git 收尾。先验证 detached HEAD、ancestry、无 unmerged entries
和无进行中的 Git 操作，然后：

```text
git reset --soft <base_sha>
git add -A
git diff --cached --quiet
```

若 cached diff 为空，记录 `no_change`。否则以固定 message 和仅限本命令的 Humanize identity
创建 commit，再验证它只有 `base_sha` 一个 parent、worktree clean，并通过 `-z` 查询 changed
paths。这个过程有意压平 writer 自己产生的任意数量提交，最终契约由协调器保证。

### 4. 集成和检查

全部 writer 都成功后，从 `base_sha` 创建 detached integration worktree。按 job 输入顺序跳过
`no_change`，逐个 cherry-pick source commit，并在每一步后记录新的 integration HEAD。冲突时
立即返回失败并保留所有现场。

cherry-pick 完成后顺序运行 checks。每条命令都使用 integration cwd 和调用方环境；返回码非零
立即失败。所有 checks 通过后必须再次确认 integration worktree 没有非 ignored 改动。

### 5. 发布和清理

发布前从主 `repo_root` 重新检查 branch、HEAD、target ref 和 status。满足启动时条件后执行：

```text
git merge --ff-only <integration_tip>
```

随后验证主 HEAD、status 和 tree。只有这些验证全部通过才清理。清理前逐个核对 managed path、
worktree 注册信息、HEAD 和 clean 状态，再使用精确路径执行 `git worktree remove --force`；该
force 只允许删除成功 worktree 中的 ignored 构建产物。失败路径一律不清理。

## 相关代码位置

- `src/hmz/runner.py`：增加 job/result 数据、Git argv helper、lease 生命周期、子进程并发、
  commit 规范化、integration、发布和清理入口；不改变 `Runner.run()`。
- `tests/test_worktrees.py`：使用临时 Git repository 和 fake argv 覆盖全部新行为。
- `tests/agents/test_agents.py`、`tests/agents/test_appservers.py`：只运行现有测试；它们已经覆盖
  普通 backend 和 Codex/Kimi metadata 使用当前进程 cwd，不增加绑定语义。
- `tests/test_async_flows.py`、`tests/test_together.py`：只运行现有测试，证明单进程 flow 和 Cycle
  语义未改变。
- `tests/test_layering.py`：只运行、不修改，证明没有新增 package layer 或反向依赖。

## 依赖与顺序

### 里程碑

1. 契约和 lease
   - 为参数/preflight、detached lease、路径边界和部分创建失败编写失败测试。
   - 实现最小 Git helper、job/result 类型和 worktree 注册。
2. 子进程隔离
   - 为实际 cwd、相同相对路径隔离、稳定结果顺序、并发上限、非零退出和中断编写测试。
   - 实现有界启动、等待和终止逻辑，不触碰 Agent 层。
3. Writer Git 收尾
   - 为未提交改动、多提交 squash、no-change、branch escape、非后代和冲突状态编写测试。
   - 实现 snapshot 规范化、单提交契约、clean 验证和 changed paths 查询。
4. 集成和发布
   - 为稳定 cherry-pick 顺序、冲突、检查失败、检查污染、发布竞争和发布后验证编写测试。
   - 实现 integration lease、checks、fast-forward 和 source/integrated commit 映射。
5. 清理和回归
   - 覆盖 ignored 构建产物、cleanup failure、错误路径拒绝和失败现场保留。
   - 运行完整回归、pre-commit、pytest 和 diff 范围审查。

### 任务拆分

| 任务 ID | 描述 | 目标验收标准 | 依赖 |
|---|---|---|---|
| task1 | 以 TDD 实现 Python 入口、参数/preflight 和 detached lease | AC-1、AC-2 | - |
| task2 | 以 TDD 实现有界子进程执行、cwd 隔离、失败等待和中断处理 | AC-2 | task1 |
| task3 | 以 TDD 实现 snapshot 规范化、multi-commit squash、no-change 和异常 Git 状态拒绝 | AC-3 | task2 |
| task4 | 以 TDD 实现顺序集成、checks、发布竞争检测和 fast-forward 发布 | AC-4、AC-5 | task3 |
| task5 | 以 TDD 实现成功清理、cleanup error 和全部失败现场保留 | AC-6 | task4 |
| task6 | 审查子进程/Git 边界，修正问题并运行完整质量门槛 | AC-1 至 AC-7 | task5 |

## 实现说明

- 代码和注释不得出现 `AC-`、Milestone、Step、Phase 等计划术语，使用领域命名。
- 不修改任何 `SPEC.md`、README、CLI、Agent 配置、machine 或 backend 实现。
- 所有 Git 和 writer/check 子进程都使用 argv list 与显式 `cwd`；不得依赖父进程 cwd 变化。
- Git helper 的错误应包含操作、cwd、return code 和 stderr，但不得记录完整环境或凭据。
- 每创建一个 lease 就立即登记；任何异常结果必须能列出已经创建并保留的精确路径。
- 同一 repository 内的 worktree add/remove、commit 规范化和 cherry-pick 保持串行；只有 writer
  子进程阶段并行。
- job stdout/stderr 沿用现有进程流，不在结构化结果中复制完整 transcript。
- 测试不得调用真实 Claude、Codex、Kimi 服务；fake writer 通过 argv 参数获得测试所需的
  barrier、内容和退出状态。
- 实现完成后必须运行：

  ```sh
  uv run pre-commit run --all-files
  uv run pytest
  ```

## 后续版本候选

以下内容不属于第一版，只有在真实使用证明需要后再单独设计：

- 面向终端用户的新 CLI 入口和 TUI 聚合视图。
- 单个父 Cycle 关联多个 writer 子 Cycle 的 manifest。
- crash resume、显式 cleanup/GC 命令和长期结果持久化。
- dirty tree snapshot、stash 搬运、submodule/LFS、跨 repository job。
- remote/container writer、资源配额、安全沙盒或恶意 Git 命令防护。
- 自动冲突解决、语义合并、自动 rebase 或部分 writer 发布。
