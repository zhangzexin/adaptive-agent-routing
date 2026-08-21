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
- 可选的 `children=luna-max` 资源约束模式把所有实际子代理硬锁定为 `gpt-5.6-luna / max`；省略该指令时解析为 `child_policy=adaptive`，已解析的 profile 仍继续对合格候选排序。
- `profile=economy` 不再只是提示词偏好：账本会记录每个自动/回退节点的定性排序或可重算成本向量，校验器会拒绝不完整候选、算错的总成本、非最低成本选择，以及预计不如父会话划算的量化委派。

## 为什么 Luna 从 xhigh、Terra 从 high 起步

V2 优化的是包含重试、返工、审核和升级在内的预期总成本，而不是第一次调用的标价。因此，即使较低强度的单次价格更低，只要更容易产生这些后续成本，它们就可能更贵、更慢。V2 采用家族特定的保守质量下限：Luna 从 `xhigh` 起步，Terra 从 `high` 起步；完整公式和证据限制见 [校准说明](references/calibration-and-evaluation.md)。

这不是 OpenAI 官方限制，也不是声称被排除的组合没有任何用途。它是用户选择的、可撤销的预期总成本策略；如果以后有可比的本地数据证明某个严格限定场景值得重新纳入，应通过显式版本化修改和回归测试完成，而不是由排行榜刷新自动改变。

显式用户指定仍可在运行时支持时保留，但被排除的组合属于 V2 认证范围外选择，不能写进 V2 路由计划，也不能靠计划中的 `explicit_user` 自证授权。此时应把工作留在被固定的父代理、取得用户对另一合格子组合的许可，或说明 V2 无法认证该委派；权限、安全、任务语义和验证要求始终不变。父任务被固定到某个组合，并不自动表示用户也允许所有子任务继承该组合。

## 激活边界

- 只有显式调用 `$adaptive-agent-routing` 或在 UI 中选择本 Skill 时才启用。
- 调用本身授权根代理判断是否值得委派，不代表必须创建子代理。
- `children=luna-max` 只限制子代理，不改变主会话模型，也不会强迫不合适的节点离开主会话。
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

调用语法：

```text
$adaptive-agent-routing [profile=<balanced|latency|economy|quality>] [children=luna-max] <任务>
```

两个修饰符各最多出现一次、顺序可交换。省略 `profile=` 时解析为 `balanced` 并在账本中显式记录；省略 `children=` 时解析为 `adaptive`。未知值、重复值或冲突值必须停止解析并公开报错，不能静默回退。

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
| `economy` | 在合格候选中比较包含重试、返工、审核、升级和协调开销的预期总成本，并判断委派是否优于父会话 |
| `quality` | 提高保守质量带并加强独立验证；不是所有节点都使用 Max |

档位只排序已合格候选，不降低权限、安全、能力或验证下限。每次依赖指标的选择都应披露 `METRIC_SOURCE`；来源不是 `none` 时还要给出 `METRIC_AS_OF` 与 `EVIDENCE_ID_OR_WINDOW`。

| 调用方式 | 解析后的 profile | child policy | 子代理候选池 |
| --- | --- | --- | --- |
| 无修饰符 | `balanced` | `adaptive` | 正常合格候选 |
| `profile=economy` | `economy` | `adaptive` | 正常合格候选 |
| `children=luna-max` | `balanced` | `luna_max_only` | 仅 Luna Max |
| `profile=economy children=luna-max` | `economy` | `luna_max_only` | 仍仅 Luna Max |

### `profile=economy` 的可验证行为

Economy 先应用全部能力、权限、安全、风险和验收下限，再处理成本；它不能让原本不合格的模型/强度重新进入候选池。每个由 Economy 自动选择或回退选择的子节点都必须包含 `economy_evaluation`：

| 评估模式 | 使用条件 | 校验行为 |
| --- | --- | --- |
| `qualitative` | 没有可比较的运行时/本地成本数据，或只有 `community_prior` | 完整列出合格候选的定性顺序，所选组合必须排第一；报告明确标记“仅定性”，不得宣称量化省钱 |
| `quantitative` | `METRIC_SOURCE` 为 `runtime` 或 `local_telemetry`，且任务 cohort、工具面和成本单位可比较；这两种来源不得退回定性模式 | 为所有合格候选及实际父组合记录同口径成本向量；校验器重算总成本，执行固定并列规则，并要求所选子组合既是最低值又低于父会话基线 |

量化模式使用版本化公式：

```text
E[C_total] =
    C_initial
  + P(retry)     * E[C_retry | retry]
  + P(rework)    * E[C_rework | rework]
  + C_review
  + P(escalation)* E[C_escalation | escalation]
  + C_coordination
```

候选和父会话估计都必须记录完整成本向量、样本量和唯一证据引用；每个引用必须位于根账本 `EVIDENCE_ID_OR_WINDOW#<record-id>` 命名空间内，父估计的组合还必须等于实际 orchestration parent。成本输入有限、非负且不超过 `10^15`，所有数值最多六位小数；校验器用十进制定点和 half-even 舍入重算，不使用会随数值规模放大的浮点相对容差。`expected_total_cost` 与公式不符、候选覆盖不完整、存在更低成本候选，或所选子组合不低于 `parent_estimate.expected_total_cost` 时，校验器会拒绝路由。六位定点值相同才按规范化 `<model, family, effort>` 键排序，避免随候选书写顺序漂移。

显式用户固定和受保证的父组合继承优先于 Economy 排序；这种节点不会伪造 `economy_evaluation`，最终报告会显示 profile 被该选择来源绕过。父会话执行的步骤不属于 `nodes`；定量评估判定 `keep_parent` 的工作必须留在父会话，而不是写成子节点。

## Luna-Max-only 子代理资源约束模式

额度紧张、希望把子任务集中到 Luna 家族时，可显式把所有子代理锁定为 Luna Max。这里的“资源约束”只表示限制子代理候选池，不是未经运行时数据证明的账单、配额或耗时承诺：

```text
$adaptive-agent-routing children=luna-max <任务>
$adaptive-agent-routing profile=economy children=luna-max <任务>
```

`children=luna-max` 与 `profile=` 正交：profile 仍决定是否值得委派、如何排序和调度合格节点；资源约束模式则把子代理候选池硬限制为唯一组合：

```json
{"model":"gpt-5.6-luna","family":"luna","effort":"max"}
```

其机器字段是 `"child_policy": "luna_max_only"`。未带指令时使用 `"child_policy": "adaptive"`；为兼容已有 V2 账本，省略该字段也按 `adaptive` 处理。

Luna-Max-only 的边界是：

- 每个实际 spawn 都显式同时传 `model=gpt-5.6-luna` 与 `reasoning_effort=max`，并继续使用模型/强度优先的任务名和完整回执链；
- 禁止父模型继承、Terra/Sol/Luna `xhigh` 回退、模型默认强度和任何“近似等价”替代；
- 只委派结构化、上下文封闭、验收 oracle 足够强、非高风险、非跨系统的叶子节点；架构、未知根因诊断、通用型实现、高风险工作和独立终审留在主会话；
- Luna Max 不在当前运行时目录时只能保留为未派发的 `planned` 目标或完全留在主会话，不能进入 `dispatched/completed`；精确 spawn 尝试被拒时，账本可记录为 `dispatch_blocked`；
- 第一次 spawn 前冻结 `runtime.available_pairs`，并记录带时间、证据引用和规范化 `available_pairs_sha256` 内容摘要的 `runtime.catalog_snapshot`；最终审计会核对摘要并保留派发时快照，不用后来变化的目录抹掉已经接受的历史回执。运行时目录若在剩余节点派发前变化，应停止并用新账本重新验证；
- 每个节点声明稳定的 `work_unit_id`；真正的瞬时错误必须由主会话在失败结果上记录 `failure_classification=transient` 和非空 `failure_evidence`，才可用相同 executor、相同契约和 `retry_of`/`retry_kind=transient` 显式重试一次，而且 retry 的 spawn 必须发生在该失败结果之后。确定性验证失败或其他实质性失败不得重试，也不得换节点名或工作单元 ID 继续交给 Luna Max。
- 每次 spawn 尝试（包括拒绝）和每个子代理结果都立即追加一个全局唯一、从 1 连续递增且不可重排的 `event_seq`。最早的非 `success` 结果或最终 `dispatch_blocked` 尝试形成唯一失败栅栏；栅栏后的新 spawn 全部停止，唯一例外是该最早失败初始节点的一次合法瞬时重试。更晚失败的并行 sibling 不会获得第二个 retry 例外；同 wave 但在栅栏前已派发的子代理可以完成，尚未派发的节点移回主会话。

`max_uses=1` 表示每个节点最多有一个被运行时接受的 Max 子代理；被拒绝且未创建子代理的 dispatch 尝试不算一次 Max 执行。若一个已经创建的子代理因真正的瞬时原因失败，唯一允许的跨节点重试会作为同一 `work_unit_id` 下的第二个、也是最后一个节点记录。

因此它是“所有已创建子代理都使用 Luna Max”的模式，不是“所有工作都交给 Luna”的模式。对不适合 Luna 的节点保持主会话执行，才能避免用多轮返工抵消单次调用的节省。

实际 Plus 配额扣减、计费和耗时仍以当前运行时为准；本 Skill 不承诺固定节省比例。若没有可比较的运行时或本地数据，只能把它视为定性的预算控制策略。

`profile=economy children=luna-max` 不会寻找更便宜的子模型，也不会把 Luna Max 降到较低强度。此时子候选只有一个，Economy 仍需判断该 Luna Max 子节点是否比父会话执行更值得，并决定哪些合格节点占用有限并发；它不能改变实际子代理的精确组合。

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

账本 schema 为 `aar.routing-ledger.v2`。它有意拒绝早期草案的 `aar.routing-plan.v2`，因为后者只有计划选择、没有实际派发证据。根状态分为 `planning`、`active`、`finalized`；节点状态分为 `planned`、`dispatched`、`completed`、`dispatch_blocked`。根字段 `child_policy` 可取 `adaptive` 或 `luna_max_only`；旧账本省略时按 `adaptive`。校验器使用 Python 标准库，只读，不修改账本或工作区。除编排、DAG、运行时组合、质量护栏和 reviewer 契约外，它还检查：

- 显式派发是否同时传了模型与强度；
- 完整历史继承是否没有混入显式覆盖；
- 任务名是否以精确组合开头、用户标签是否含精确组合；
- 接受回执、有效组合和选择记录是否一致；
- 子代理返回的组合回声是否与回执一致；
- 未解析或拒绝状态是否被错误包装成已确认。
- Economy 自动/回退节点是否包含完整定性顺序或同口径量化成本向量，预期总成本能否重算，所选组合是否为确定性最低值，以及量化委派是否优于父会话基线。
- Luna-Max-only 模式是否在候选、选择、spawn 参数、有效组合和结果回声的每一层都保持精确的 Luna Max，且没有继承、回退或实质性同级返工预算。
- Luna-Max-only 工作单元是否只有一个初始节点、其失败是否有主会话核验的瞬时分类和证据、重试是否发生在失败结果之后、是否至多一个直接关联且契约不变的瞬时重试，以及总派发次数是否超过预算。
- Luna-Max-only 事件序号是否全局唯一、连续、按真实记录顺序追加，以及失败栅栏后是否出现了伪装成同 wave、新节点或新 work unit 的额外派发。
- Luna-Max-only 的实际派发是否发生在全部依赖成功结果之后；较大的 wave 数本身不能替代事件顺序证据。

账本最终化后生成用户可直接核验的逐子代理报告：

```bash
python scripts/validate-routing-plan.py path/to/ledger.json --report
```

固定列为：

```text
agent | role | requested pair | effective pair | confirmation | receipt | result | purpose
```

报告会在表格后显示已解析的 `profile`、`metric_source` 和 `child_policy`，保持原有表格首行和列顺序兼容。Economy 还会显示逐节点评估模式、所选组合、子/父预期成本、成本单位、委派决定和依据；没有量化证据或被显式固定/继承绕过时也会明确标出。存在回退时同时显示请求和实际组合；`receipt` 列按顺序保留全部尝试的接受/拒绝回执；Luna-Max-only 的回执和结果会附带 `e<event_seq>`，非成功结果同时显示失败分类；派发被拒绝时有效组合留空并显示 `runtime-rejected`。`--report` 会拒绝尚未最终化的账本。

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
