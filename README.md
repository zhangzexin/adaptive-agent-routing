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

该模式不会强制创建子代理，也不会改变当前父模型。它只在需要分派时固定优先采用以下 GPT-5.6 映射：

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
| Deep architect/reviewer | 架构、关键决策、安全分析、疑难诊断、终审 | 当前最强深度推理模型；优先 Sol |
| General worker | 多文件实现、常规调试、工具密集型工作、集成 | 当前均衡生产模型；优先 Terra，其次 Sol |
| Fast leaf | 清晰、短小、可独立验收的执行任务 | 当前最快的合适叶子模型；优先 Luna，最低 `xhigh` |

Luna 不承担开放式设计、未知根因调试、长链规划、跨模块整合或最终综合。如果 Luna 不支持 `xhigh`/`max`，则视为不可用并回退到 Terra。

## 回退顺序

1. Luna 或所需强度不可用：回退到 Terra `medium/high`。
2. Terra 不可用：使用当前运行时默认的常规模型。
3. Sol Max 不可用：使用当前暴露的最强深度模型和受支持强度。
4. 模型覆盖完全不可用：继承父代理/默认模型，但保留角色、范围和验证契约。

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
