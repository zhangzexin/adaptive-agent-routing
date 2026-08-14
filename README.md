# Adaptive Agent Routing

一个面向 OpenAI Codex 的显式启用、多代理自适应路由 Skill。

它让根代理在当前任务中自行判断是否值得使用子代理，并按照运行时实际暴露的模型与推理强度，在深度设计/审核、常规执行和快速叶子任务之间分派工作。

> 这是社区 Skill，不是 OpenAI 官方功能或官方路由策略。`strict-5.6` 也是本 Skill 自定义的调用关键词，不是 Codex CLI 参数。

## 核心行为

- 只有显式调用 `$adaptive-agent-routing` 或在 UI 中选择本 Skill 时才启用。
- 调用本身即授权根代理判断是否需要子代理，无需再写“请使用子代理”。
- 简单、局部、机械任务保留在父代理中执行。
- 可独立分工、可安全并行或需要独立审核时才创建子代理。
- 子代理是叶子执行者，不继续创建孙代理。
- 并行写入遵守“一份文件只有一个写入者”。
- 父代理必须检查实际文件、测试和证据后才能整合结果。
- 默认自适应模式下，深度设计/审核子代理完整继承父会话的模型与推理强度，不做升降级或替换。
- 每个已启动的子代理都显示模型与推理强度；继承值暂时不可见时先标记为继承父会话，运行后尽量补充精确值。
- 模型或推理强度不可用时按规则回退，并在最终结果中披露。
- 不修改 `AGENTS.md`、Codex 默认模型、MCP 配置或全局路由规则。

`agents/openai.yaml` 设置了：

```yaml
policy:
  allow_implicit_invocation: false
```

因此，未调用本 Skill 的任务继续遵循当前 Codex 官方默认行为，也能继续受益于后续官方改进。

## 安装

选择一个用户级 Skill 目录安装即可，不要同时安装两份同名 Skill。

### 安装到 Codex 用户目录

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/zhangzexin/adaptive-agent-routing.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/adaptive-agent-routing"
```

### 安装到跨工具用户目录

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/zhangzexin/adaptive-agent-routing.git \
  "$HOME/.agents/skills/adaptive-agent-routing"
```

Codex 通常会自动检测 Skill。若 `/skills` 或 Skill 选择器中没有出现，退出当前 Codex 进程并重新启动；不需要关闭整个终端窗口。

## 使用

### 推荐：自适应模式

```text
$adaptive-agent-routing <任务>
```

例如：

```text
$adaptive-agent-routing 排查并修复登录后偶发白屏的问题，同时检查回归风险
```

根代理会先分类任务：

- 任务简单且局部：直接由父代理完成。
- 常规多文件实现或调试：使用合适的常规执行代理。
- 架构、安全、关键决策或终审：补派深度设计者/审核者。
- 多个任务真正独立且文件所有权不重叠：并行分派。

### 可选：`strict-5.6` 模式

```text
$adaptive-agent-routing strict-5.6 <任务>
```

该模式不会强制创建子代理，也不会改变当前父模型。它只在需要分派时固定优先采用以下 GPT-5.6 映射；其中深度设计/审核角色会显式覆盖为 `gpt-5.6-sol` / `max`，忽略父会话的模型与推理强度：

| 工作类型 | 首选模型 | 推理强度 |
| --- | --- | --- |
| 关键设计、安全分析、重要推理、最终审核 | `gpt-5.6-sol` | `max` |
| 常规实现与普通调试 | `gpt-5.6-terra` | `medium`，复杂/高风险写入使用 `high` |
| 清晰、短小、边界稳定的叶子任务 | `gpt-5.6-luna` | 最低 `xhigh`；短而难时使用 `max` |

如果指定模型或强度未由当前运行时暴露，Skill 会使用回退链继续任务并报告替换。日常使用建议采用自适应模式，以便未来自动利用新的官方模型能力。

目前只定义了 `strict-5.6`。`strict-5.5` 等其他 `strict-*` 关键词没有固定映射，不应视为受支持模式。

## 自适应角色

| 角色 | 适合的任务 | 路由偏好 |
| --- | --- | --- |
| Deep architect/reviewer | 架构、关键决策、安全分析、疑难诊断、终审 | 完整继承父会话模型与推理强度；不做覆盖 |
| General worker | 多文件实现、常规调试、工具密集型工作、集成 | 当前均衡生产模型；优先 Terra，其次 Sol |
| Fast leaf | 清晰、短小、可独立验收的执行任务 | 当前最快的合适叶子模型；优先 Luna，最低 `xhigh` |

默认自适应模式下，`deep_review` 等深度角色启动时不传模型或推理强度覆盖，并使用完整历史继承。命名前必须先读取当前任务最新的实时模型信息；在本地 Codex CLI/桌面环境中，可从当前任务会话记录的最新 `turn_context` 只读取模型与推理强度字段。只有这些实时来源都不可用时才使用临时标签，且不能因此取消有价值的子代理。只有 `strict-5.6` 模式会让深度角色忽略父会话设置并使用固定映射。

Luna 不承担开放式设计、未知根因调试、长链规划、跨模块整合或最终综合。如果 Luna 不支持 `xhigh`/`max`，则视为不可用并回退到 Terra。

## 子代理模型标签

实际模型与推理强度在启动前可知时，从同一组值生成两种名称：

- 用户可见标签：`deep_review (gpt-5.6-sol, max)`。
- Codex 内部任务名：`deep_review_gpt_5_6_sol_max`。

内部 `task_name` 只能使用小写字母、数字和下划线，所以不能直接包含括号、连字符与逗号。启动成功后，父代理应在进度说明中展示用户可见标签，并将同一标签及 `confirmed` 状态写入分派包。发生模型回退时，必须按回退后的实际模型与强度重新生成名称；失败尝试的名称不能作为最终显示结果。父代理生成的标签是最终依据；`AGENT_LABEL` 只是分派提示字段，不是 `spawn_agent` 的正式命名参数，也不能靠子代理回显来修改桌面端名称或验证实际运行配置。

不要把 `deep_review_inherit_parent` 当成正常名称；桌面端会把它显示成容易误解的“Deep review inherit parent”。如果读取实时元数据后仍无法在启动前解析继承值，使用中性临时内部名称 `deep_review_runtime_pending`、用户可见标签 `deep_review (parent runtime pending)` 和 `MODEL_LABEL_STATUS: provisional`。创建后通过子线程或运行时信息尽快解析实际值，并在后续进度中统一显示例如 `deep_review (gpt-5.6-sol, xhigh)`。

已创建子代理的内部 `task_name` 不能事后修改；当前 `spawn_agent` 与协作工具没有重命名操作。后续解析出的模型与强度可以补充到进度和最终报告中，但不会改掉桌面端已有条目。只有用户明确要求桌面名称必须精确时，才考虑用正确 `task_name` 新建替代子代理；不要为了纯显示问题擅自重启正在进行的有效工作。

如果运行后仍拿不到精确值，继续执行任务并明确说明“继承父会话，但当前客户端未暴露解析后的值”，不要猜测模型或强度。标签信息不足本身不能阻止有价值的子代理分工。

## 回退顺序

1. Luna 或所需强度不可用：回退到 Terra `medium/high`。
2. Terra 不可用：使用当前运行时默认的常规模型。
3. 仅在 `strict-5.6` 模式下，Sol Max 不可用时使用当前暴露的最强深度模型和受支持强度。
4. 默认自适应模式的深度角色不进入模型选择回退链，始终完整继承父会话模型与推理强度。
5. 非深度角色无法使用模型覆盖时，继承父代理/默认模型，但保留角色、范围和验证契约。

## 协作约束

- 根代理负责规划、所有权、依赖顺序、结果核验和最终整合。
- 子代理收到自包含的分派包，包含目标、范围、必读文件、禁止操作、交付物、验证和停止条件。
- 同一个文件不能被多个写代理并行修改。
- 默认最多同时使用三个子代理，为父任务保留运行时额度。
- 临时错误只重试一次；同类失败再次发生时升级诊断或返回用户，不继续盲目扩散代理。
- 子代理输出只是证据，不是最终权威。

## 兼容性

- 需要当前 Codex 会话暴露原生子代理工具。
- 模型名称和推理强度以运行时目录为准；不同账号、CLI、桌面 App 或版本可能暴露不同能力。
- 开发验证基线为 Codex CLI `0.147.0`。建议使用该版本或更新版本。
- 桌面 App 的内置运行时可能与 Homebrew CLI 不同；缺少 Luna 时会自动回退。
- Skill 只携带路由指令，不携带模型权限、账号权限、API Key 或第三方 provider 配置。

## 更新

如果安装目录是 Git clone：

```bash
git -C "${CODEX_HOME:-$HOME/.codex}/skills/adaptive-agent-routing" pull
```

更新后 Codex 通常会自动检测；若仍显示旧内容，重新启动 Codex 进程。

## 文件结构

```text
adaptive-agent-routing/
├── README.md
├── SKILL.md
└── agents/
    └── openai.yaml
```

## 设计参考

- [OpenAI Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills)
- [ZypherHQ Agent Orchestration Skill](https://github.com/ZypherHQ/agent-orchestration-skill)
- [wshobson/agents Task Coordination Strategies](https://github.com/wshobson/agents)
- [Gentle AI SDD Orchestrator](https://github.com/Gentleman-Programming/gentle-ai)
