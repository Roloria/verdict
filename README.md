# ai-verdict

[English](README.en.md) · 简体中文

**AI 输出质量闸门**：不是让另一个模型打分，而是让每条断言绑定一个可执行检查。
模型负责提出 claim，确定性工具负责裁决，CI 只看退出码。

> fork 自 [reverify](https://github.com/2akouwu/reverify)（MIT, v0.11.0）。
> `reverify/` 是 vendored 上游，永不改动；所有新代码在 `verdict/`，因此
> `git merge upstream/main` 永远无冲突。上游原文见 [README.upstream.md](README.upstream.md)。

---

## 为什么

「让 LLM 给 AI 输出打分」是当前主流做法，但一个与生成器共享先验的裁判，给你的只是数字，不是证据。有项目把结论写得很直白：

> LLM judges agree with human slop labels at chance.

verdict 把问题换成：**这句话能被工具验证吗？** 不能验证的，就不是 claim，是散文。

一次运行输出：37 条断言，34 条 VERIFIED，2 条 REFUTED，1 条 INCONCLUSIVE，每条附带实际观测到的证据与复现命令。

## 快速开始

```bash
pip install ai-verdict            # 发布前：pip install -e ".[dev]"
verdict kinds                     # 查看全部闸门类型
verdict rules list                # 查看规则包

verdict check report.md --rules ai-tells-density,secrets-pii
verdict check report.md --rules ai-tells-density --report gate.html
```

退出码：`0` 通过 · `2` 有断言被驳回 · `3` 证据太薄 · `4` 有结论未定（`--strict`）。

## 核心机制

| 概念 | 说明 |
|---|---|
| claim → 工具 → 证据 | 每条断言由确定性工具裁决，返回 `VERIFIED` / `REFUTED` / `INCONCLUSIVE` 与实际观测值 |
| 信息量 > 通过率 | 30 条都通过但全是废话不算证据；同类型断言按 `1/N` 递减计权，太薄就 exit 3 |
| 权重防灌水 | 重述已知事实、重复、自引用的断言权重为 0 |
| 证据账本 | 每次运行追加一行到 `.verdict/ledger.jsonl`（时间、产物哈希、计数、退出码） |
| fail-closed | 工具跑不起来是 `INCONCLUSIVE`，不是 `VERIFIED` |
| 无模型验证路径 | 验证链里没有 LLM；LLM 只能提出 claim，不能裁决 |

### 闸门类型

| gate | 断言 |
|---|---|
| `text_present` / `text_absent` | 字面量或正则出现 / 不出现（可限次数） |
| `slop_density` | 单个段落里不同 AI 味模式少于 N 个（内置 192 短语 / 59 类） |
| `file_exists` | 声称交付的文件确实存在且非空，路径不得越出仓库 |
| `command_succeeds` | 白名单命令按预期退出（argv-only，字符串直接拒绝，未列名不执行） |
| `diff_touches` | 声称改动的路径确实出现在 git diff 里 |
| `tests_actually_prove` | 没有删测试、跳过测试、或「改了代码却没动测试」 |
| `citation_resolves` | 报告里的 `path:line` 引用真实存在，并返回实际行内容作证据 |

另支持全部 reverify 类型（`bytes_at`、`string_present`、`functions_equiv` ...）。

### 规则包

`ai-tells-density`（低误报默认）、`ai-tells`（严格版）、`secrets-pii`、`pr-evidence`。
团队可用 `verdict rules add ./house-style.json` 把规则包 vendor 到 `.verdict/rules/`。

## 中英文切换

**项目同时支持 `zh-CN` 与 `en`，新增语言只需往 `verdict/i18n.py` 加一份语言表。**

| 方式 | 示例 |
|---|---|
| 命令行 | `verdict check ... --lang en`（也可 `verdict --lang en check ...`） |
| 环境变量 | `VERDICT_LANG=en` |
| 项目配置 | `.verdict/config.json` → `{"lang": "zh-CN"}`（示例见 `config.example.json`） |
| 跟随系统 | `--lang auto`（读 `LC_ALL` / `LANG`） |
| 报告页 | 单文件 HTML 内嵌双语，右上角按钮即时切换，离线可用 |

优先级：`--lang` > `VERDICT_LANG` > 项目配置 > 默认 `zh-CN`。

**永不翻译**：协议值（`VERIFIED` / `REFUTED`）、gate 名、`--json` 输出、证据字段名（JSON）、claim 文件。这样 CI、脚本和上游协议都不受语言影响；只有面向人的文案会变。

```bash
verdict check report.md --rules ai-tells-density --lang zh-CN --report gate.zh.html
verdict check report.md --rules ai-tells-density --lang en    --report gate.en.html
```

## 确定性审查范围（借鉴 open-code-review）

```bash
verdict scope --mode workspace --json
verdict scope --mode merge-base --base main --to HEAD --delegate --json
```

输出每个变更文件的明确入选/排除理由、按文件解析出的规则包、以及测试文件配对后的分桶；`--delegate` 生成结构化 agent 移交说明，不调用任何模型。
设计借鉴自 [alibaba/open-code-review](https://github.com/alibaba/open-code-review)（Apache-2.0），未复制其代码或数据，见 [ATTRIBUTION.md](ATTRIBUTION.md)。

## CI / Agent 入口

```yaml
- uses: Roloria/verdict@v1
  with:
    target: docs/report.md
    rules: ai-tells-density,secrets-pii
    lang: zh-CN
```

- `SKILL.md` / `skills/ai-verdict/SKILL.md`：Agent Skills 生态，`npx skills add Roloria/verdict --skill ai-verdict`
- `ai-verdict-mcp`：stdio MCP server，工具 `verify_claims` / `list_rules`，支持 `lang` 参数
- `.github/workflows/verdict.yml`：本仓库自闸（含「脏样例必须 exit 2」的反向测试）

## 基准

`python eval/run.py` → [eval/RESULTS.md](eval/RESULTS.md)：30 个注入缺陷样例，
precision / recall / F1 = 1.000 / 1.000 / 1.000，0 漏放、0 误报，按缺陷类型分解。
定位是回归绊线，不是通用准确率声明。

## 当前状态

| 项 | 状态 |
|---|---|
| 代码 | 完整，全量测试 381+ passed / 55 skipped，自闸 10/10 |
| PyPI / Marketplace | **未发布** —— 包名 `ai-verdict`（原 `verdict-gate` 已被同名项目占用） |
| 待办 | 一次性配 PyPI trusted publisher → `v0.12.0` tag → Marketplace，见 [RELEASE.md](RELEASE.md) |

## 文档

[USAGE.md](USAGE.md) · [VISION.md](VISION.md) · [ITERATION-PLAN.md](ITERATION-PLAN.md) · [SKILL.md](SKILL.md) · [RELEASE.md](RELEASE.md) · [ATTRIBUTION.md](ATTRIBUTION.md)

License: MIT. 上游 reverify (MIT)、AI 味模式 FeedHive/ai-slop-detector (MIT) 的归属见 ATTRIBUTION.md。
