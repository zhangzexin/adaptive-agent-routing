# Adaptive Agent Routing V2

一个面向 OpenAI Codex 的显式启用、多代理契约式路由 Skill。

V2 不再使用“角色 → 固定模型/强度”的映射，而是按下面的顺序决策：

```text
任务契约
  → 可验证性与风险要求
  → 枚举合格模型/强度组合
  → 与当前运行时能力取交集
  → 应用质量护栏
  → 按目标档位排序
  → 有界派发
  → 记录真实 spawn 参数与运行时回执
  → 对照子代理回声
  → 父代理基于实际证据验收
```

> 这是社区 Skill，不是 OpenAI 官方路由策略。模型家族语义参考 OpenAI 官方文档；V2 的自动排除、排序、回退和验收规则是本工作流的可版本化策略。

## V2 的核心变化

- 模型家族与推理强度分开选择：家族看任务开放性和耦合，强度看难度、风险和验证难度。
- 所有 V2 认证子路由统一排除 Luna `low`/`medium`/`high` 和 Terra `low`/`medium`，覆盖自动选择、回退、继承与显式用户来源；简单任务通常留在父代理。
- Luna 只承担封闭、可重复、可精确验收的结构化节点。OpenAI 将 Luna 定位为快速且经济，但 V2 不假定每个 Luna × 强度组合在所有任务上都有更低的端到端墙钟时间。
- 继承与回退都必须重新通过当前节点的能力下限；不再使用固定字符串回退链。
- Sol `xhigh` 是常见深度工作偏好，Max 只用于最难的单一节点；Ultra 仅作为根任务编排层，显式子代理不使用 Ultra。
- 并行写入按文件和语义冲突域隔离；复杂或高风险计划可用确定性脚本检查 DAG、并发、路由与验证契约。
- 每个实际子代理必须公开精确模型与推理强度，并形成“计划 → spawn 参数 → 接受回执 → 有效组合 → 子代理回声 → 最终表格”的可审计链；`selected_pair` 本身不算执行证明。

## 为什么 Luna 从 xhigh、Terra 从 high 起步

V2 优化的是包含重试、返工、审核和升级在内的预期总成本，而不是第一次调用的标价。因此，即使较低强度的单次价格更低，只要更容易产生这些后续成本，它们就可能更贵、更慢。V2 采用家族特定的保守质量下限：Luna 从 `xhigh` 起步，Terra 从 `high` 起步；完整公式和证据限制见 [校准说明](references/calibration-and-evaluation.md)。

这不是 OpenAI 官方限制，也不是声称被排除的组合没有任何用途。它是用户选择的、可撤销的预期总成本策略；如果以后有可比的本地数据证明某个严格限定场景值得重新纳入，应通过显式版本化修改和回归测试完成，而不是由排行榜刷新自动改变。

显式用户指定仍可在运行时支持时保留，但被排除的组合属于 V2 认证范围外选择，不能写进 V2 路由计划，也不能靠计划中的 `explicit_user` 自证授权。此时应把工作留在被固定的父代理、取得用户对另一合格子组合的许可，或说明 V2 无法认证该委派；权限、安全、任务语义和验证要求始终不变。父任务被固定到某个组合，并不自动表示用户也允许所有子任务继承该组合。

## 激活边界

- 只有显式调用 `$adaptive-agent-routing` 或在 UI 中选择本 Skill 时才启用。
- 调用本身授权根代理判断是否值得委派，不代表必须创建子代理。
- 后续“不要使用子代理”的指令优先。
- 子代理始终是叶子，不再创建孙代理，也不再次调用本 Skill。
- 路由仅作用于当前任务，不修改 `AGENTS.md`、`config.toml`、自定义代理、MCP 或未来任务。
- `agents/openai.yaml` 保持 `allow_implicit_invocation: false`，避免未选择 Skill 的任务被自动接管。

## 家族与强度

OpenAI 当前官方产品定位可概括为：

| 家族 | OpenAI 官方产品定位 |
| --- | --- |
| Sol | 复杂、开放、高价值且需要判断与润色的工作 |
| Terra | 日常工作的均衡主力 |
| Luna | 快速且经济，面向清晰、具体、可重复的工作 |

下表是 V2 在官方定位之上增加的本地自动偏好，不是 OpenAI 能力边界：

| 工作形态 | 常见候选 |
| --- | --- |
| 提取、分类、批量转换、精确核对 | Luna `xhigh` |
| 孤立且可精确测试的代码叶子 | Luna `xhigh`；Max 仅用于短而难的非关键路径节点 |
| 普通实现、调试、跨文件执行 | Terra `high`/`xhigh` |
| 未知根因、架构、开放式诊断 | Sol `high`/`xhigh` |
| 安全、权限、迁移、并发、终审 | Sol `xhigh`；Max 仅用于最难的单节点审查 |

最终候选仍以当前 `spawn_agent` 工具实际暴露并接受的模型/强度为准。Skill 不发明不可用的模型 slug，也不把社区榜单当能力权限表。

## 目标档位

```text
$adaptive-agent-routing profile=balanced <任务>
$adaptive-agent-routing profile=latency <任务>
$adaptive-agent-routing profile=economy <任务>
$adaptive-agent-routing profile=quality <任务>
```

| 档位 | 作用 |
| --- | --- |
| `balanced` | 默认；在合格候选中兼顾首轮可靠性、关键路径时间和预期总成本 |
| `latency` | 使用可比较的墙钟时间证据优化关键路径；无实测时只能做定性选择 |
| `economy` | 比较包含失败和返工在内的预期总成本；不只看标价 |
| `quality` | 提高保守质量带并加强独立验证；不是所有节点都使用 Max |

档位只排序已合格候选，不降低权限、安全、能力或验证下限。每次依赖指标的选择都应披露 `METRIC_SOURCE`；来源不是 `none` 时还要给出 `METRIC_AS_OF` 与 `EVIDENCE_ID_OR_WINDOW`。

## `strict-5.6` 迁移

V1 的 `strict-5.6` 会固定选择 Terra `medium`，与 V2 的自动质量护栏冲突，因此不再执行。

如果调用中出现：

```text
$adaptive-agent-routing strict-5.6 <任务>
```

V2 会停止路由并要求改用 `balanced`、`latency`、`economy`、`quality`，或明确指定当前运行时支持的模型/强度。它不会静默把旧名称解释成新策略。

## 编排与验收

根代理先确认权限、Ultra/编排状态和集成能力，再只为收益超过协调成本的节点建立完整契约。候选组合必须先通过语义、质量与运行时过滤；只有依赖就绪且冲突域不重叠的节点可以并行。子代理结果始终只是证据，由父代理检查实际状态并完成集成；高风险工作还需要独立只读 reviewer。失败必须先分类，再决定补上下文、重建 DAG、加强验证、升级或停止。

### 模型与强度如何做到可验证

V2 只允许两种有效派发：

| 模式 | spawn 参数 | fork | 确认状态 |
| --- | --- | --- | --- |
| 显式 | 同时传入精确 `model` 与 `reasoning_effort` | `none` 或受支持的正整数历史片段 | `confirmed-explicit` / `fallback-confirmed` |
| 继承 | 两项都不传，但父模型与强度必须已知且合格 | `all`，使用当前协作契约保证的完整继承 | `confirmed-inherited` |

只传模型不传推理强度时，运行时可能采用该模型的默认强度，因此记为 `default-unresolved` 并拒绝；父组合未知时记为 `inherited-unresolved` 并拒绝。`runtime-rejected` 表示该次调用没有创建子代理。这些状态不得包装成“已确认”。

每次派发前都必须显示 `<role> (<model>, <effort>)`，任务名固定使用“模型与强度优先”的编码：

```text
<model-slug>_<effort>_<node>_a<attempt>
```

例如 `gpt_5_6_terra_high_parser_fix_a1`。Codex 桌面端不保证提供独立的模型/强度字段，而且窄栏可能截断任务名右侧，因此精确组合必须放在最左边。任务名只让 UI 中的派发意图可见；真正的执行证据仍是已接受的显式参数或受保证的精确继承回执。任务名在创建后不可变，技能升级不会追溯改写旧任务。

## 路由账本校验器

对复杂手工扇出或高风险计划，先按 [账本契约](references/contracts-and-orchestration.md) 生成 JSON，并在派发前、回执变化后、最终报告前分别运行：

```bash
python scripts/validate-routing-plan.py path/to/ledger.json
```

账本 schema 为 `aar.routing-ledger.v2`。它有意拒绝早期草案的 `aar.routing-plan.v2`，因为后者只有计划选择、没有实际派发证据。根状态分为 `planning`、`active`、`finalized`；节点状态分为 `planned`、`dispatched`、`completed`、`dispatch_blocked`。校验器使用 Python 标准库，只读，不修改账本或工作区。除编排、DAG、运行时组合、质量护栏和 reviewer 契约外，它还检查：

- 显式派发是否同时传了模型与强度；
- 完整历史继承是否没有混入显式覆盖；
- 任务名是否以精确组合开头、用户标签是否含精确组合；
- 接受回执、有效组合和选择记录是否一致；
- 子代理返回的组合回声是否与回执一致；
- 未解析或拒绝状态是否被错误包装成已确认。

账本最终化后生成用户可直接核验的逐子代理报告：

```bash
python scripts/validate-routing-plan.py path/to/ledger.json --report
```

固定列为：

```text
agent | role | requested pair | effective pair | confirmation | receipt | result | purpose
```

存在回退时同时显示请求和实际组合；`receipt` 列按顺序保留全部尝试的接受/拒绝回执；派发被拒绝时有效组合留空并显示 `runtime-rejected`。`--report` 会拒绝尚未最终化的账本。

退出码：`0` 合法，`2` JSON/结构错误，`3` 语义策略错误，`4` 校验器内部错误。

运行回归测试：

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

脚本只能验证声明的一致性，不能证明真实模型能力、沙箱执行情况或最终任务正确性。

## 安装

选择一个用户级 Skill 目录安装，不要同时安装两份同名 Skill。

### Codex 用户目录

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/zhangzexin/adaptive-agent-routing.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/adaptive-agent-routing"
```

### 跨工具用户目录

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/zhangzexin/adaptive-agent-routing.git \
  "$HOME/.agents/skills/adaptive-agent-routing"
```

Codex 通常会自动检测 Skill 变化；如果选择器仍显示旧内容，重启 Codex 进程。

## 更新

```bash
git -C "${CODEX_HOME:-$HOME/.codex}/skills/adaptive-agent-routing" pull
```

## 文件结构

```text
adaptive-agent-routing/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── routing-policy.md
│   ├── contracts-and-orchestration.md
│   ├── validation-and-failure.md
│   ├── calibration-and-evaluation.md
│   └── routing-plan.example.json
├── scripts/
│   └── validate-routing-plan.py
└── tests/
    └── test_validate_routing_plan.py
```

## 证据与参考

- [OpenAI Models：Sol、Terra、Luna 与推理强度](https://learn.chatgpt.com/docs/models)
- [OpenAI Subagents：模型、推理、编排与自定义代理](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [OpenAI Build skills：Skill 结构、显式调用与渐进披露](https://learn.chatgpt.com/docs/build-skills)
- [V2 校准与证据边界](references/calibration-and-evaluation.md)

初始性能排序偏好部分参考了 2026-08-20 用户提供的社区截图，证据标识为 `community_prior / 2026-08-20 / user-supplied-screenshots-v1`。它们不完整、不可复现、非官方且会漂移，只能作为低置信度定性择优先验；本地可比较证据应逐步取代它们。
