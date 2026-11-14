# 迭代计划

[English](ITERATION-PLAN.en.md) · 简体中文

负责人：Kevin ｜ 起始：2026-09-15 ｜ 上游：2akouwu/reverify v0.11.0
最后更新：2026-11-15（P0 迭代：claim 提案、发布前检查、一键发布）

---

## 0. 当前进度

| 里程碑 | 状态 |
|---|---|
| M0 fork + 垂直切片 | ✓ 2026-09-15 |
| M1 代码域闸门 + 证据账本 | ✓ 2026-09-22 |
| M2 规则包 + HTML 报告 | ✓ 2026-09-22 |
| M3 CI + 分发（代码） | ✓ 2026-09-23 —— **发布仍待办** |
| M3.5 重启 | ✓ 2026-11-14 |
| M4 内容垂直 + 首发 | 进行中 |
| M5 团队版 | 等 M4 出现拉动力再做 |

测试：**414 passed / 55 skipped**（314 上游 + 93 verdict）。

**唯一阻塞**：还没发布。`verdict-gate` 这个名字 11/10 在 PyPI 被占用，包名改为
`ai-verdict`。GitHub `pypi` 环境已建好，`verdict release-check` 当前 7✓/1✗；
只差在 pypi.org 配一次 pending trusted publisher，然后 `sh tools/publish.sh`。
详见 RELEASE.md。

```bash
pip install -e ".[dev]"
env -u PYTHONPATH pytest verdict/tests reverify/tests -q
verdict check examples/demo-dirty.md --rules ai-tells-density,secrets-pii --report examples/gate.html
# → 1 REFUTED，exit 2，grounded_score 0.76
verdict check examples/demo-clean.md --rules ai-tells-density,secrets-pii
# → 14/14，exit 0，grounded_score 1.00
```

---

## 1. 架构约束（不可破坏）

1. **`reverify/` 只读。** 通过继承 `Verifier` 扩展，新闸门写成 `_check_<kind>`
   方法。上游合并必须永远无冲突。
2. **验证路径里没有 LLM。** 裁决者永远是工具。LLM 可以*提出* claim（M4），
   永远不能裁决。
3. **每个闸门都产出证据**，不是一个布尔值。
4. **信息量，不是通过率。** 全部验证通过但什么都没说的集合必须失败（exit 3）。
   见 §2.5 —— 这个坑我们已经踩过一次，还会再踩。
5. **永远 MIT。** 不做 open-core 双授权；变现只能靠托管服务。

---

## 2. 里程碑

### M0 · Fork + 垂直切片 —— 完成于 2026-09-15

Fork、上游测试套件跑绿、`verdict/` 包、`text_present` / `text_absent` /
`file_exists`、自己的评分规则集、带退出码的 `verdict check`。

### M1 · 代码域闸门 + 证据账本 —— 完成于 2026-09-22

- [x] `command_succeeds`：仅白名单、argv（绝不收 shell 字符串）、超时，
      证据 = 退出码 + stdout/stderr sha256 + 耗时。把「AI 说测试过了」变成
      一条 claim。未列名 → INCONCLUSIVE，绝不执行。
- [x] `diff_touches`：声称的路径必须出现在 `git diff --name-only <base>`；
      支持文件或目录匹配，`mode: all|any`。
- [x] `.verdict/ledger.jsonl`：每次运行一行 JSON（时间、产物 sha256、计数、
      信息量、退出码）。
- [x] `--fail-on {refuted,thin,inconclusive}`，团队自选严格度。
- [x] `--allowlist` 读 `.verdict/allowlist.json`，cwd 锁在仓库内。

### M2 · 规则包 + HTML 报告 —— 完成于 2026-09-22

- [x] 规则包格式（JSON）：`name`、`version`、`description`、`claims`、`weights`。
      解析顺序：`.verdict/rules/` → 内置 → 字面路径。
- [x] 内置包：`ai-tells`（24 条中英短语）、`secrets-pii`（9 条正则）、
      `pr-evidence`（测试真跑过、无占位符）。
- [x] `--rules a,b` 展开规则包并合并权重覆盖；`--rules` + `--claims-file` 可组合。
- [x] `verdict rules list|show|add` —— `add` 把团队规则包 vendor 进来。
- [x] `verdict check --report gate.html` 与 `verdict report <json> --out`。
      单文件 HTML，无 CDN，明暗双色，每行带证据与复现命令。
- [x] `--verbose` / 默认隐藏通过行（33 条规则的全量输出没法读）。

### M2.5 · 发现并修掉的设计缺陷 —— 2026-09-22

跑一个 33 条 claim 的规则包，`information = 19`。全部通过，于是「证据太薄」
闸门永远触发不了：**一堆容易过的 claim 比几条硬 claim 更值钱**，和这个指标
存在的目的完全相反。

修法：同一类型内部谐波递减 —— 同 kind 第 N 条 VERIFIED claim 计 `1/N`。同样的
跑分现在只有 2.5。REFUTED 保留完整权重，失败仍然读作「这条规则重要」。

后续要记住：**`--min-information` 与规则包规模强相关。** 内置包相对默认 `1.0`
落在 2.5 左右；写 100 条 claim 的团队必须自己调高。写进文档，别用调高权重的
方式「修」它。

### M3 · CI + 分发 —— 9/23–9/28（9/25 出行，前重后轻）

只有两个完整工作日，之后带宽低。按「什么最能让陌生人用起来」排序：

- [x] `action.yml` —— composite action：setup-python → `pip install ai-verdict`
      → 运行 → job summary 表格 + `exit-code` / `information` / `grounded`
      outputs。**9/23**（Marketplace 上架仍需 tag，见 RELEASE.md）
- [x] dist 更名 `reverify` → `ai-verdict`（v0.12.0）。保留 `reverify` /
      `reverify-mcp` 入口以兼容上游。新增 `publish-pypi.yml`（OIDC trusted
      publishing，仓库里不放 token）。**9/23** —— 实际上传仍需 PyPI 配一次。
- [x] 提交 `.verdict/claims.json` + `allowlist.json`，本仓库开始自闸
      （`verdict.yml`：干净样例必须过、脏样例必须 exit 2、自己的文档被闸、
      两套测试全绿）。**9/23**
- [ ] MCP server 暴露 `verify_claims`（对照 `reverify/mcp_server.py`），让 agent
      在运行途中就能闸自己的输出。出行周。（**已在 §7 完成**）
- [ ] skills.sh 生态的 `SKILL.md`：同一套规则，agent 入口。出行周。
      （**已在 §7 完成**）
- [ ] GitHub Pages：把 `examples/gate.html` 发布成在线样例报告。成本低、
      对首发文章杠杆高。（**已在 §7 完成 workflow**）

### M4 · 内容垂直 + 首发 —— 10/6–10/19

- [ ] `citation_resolves`：生成的报告里每个 `path:line` 或 URL 都要在仓库内
      解析得到。文档场景最有价值的事实核查闸门。（**已在 §8 完成**）
- [ ] `number_matches_source`：散文里引用的数字必须出现在指定的源文件里
      （正则 + 读文件 + 证据摘录）。
- [ ] AI 味词表 v2，参考（不复制）`sepia` / `hallmark` / `ponytail`，每条附
      误报说明。（**已由 §7 的 120 模式密度方案替代**）
- [ ] 首发文章：「LLM 裁判与 slop 标注的一致性等于随机」+ 脏/净样例对比。
      HN、r/LocalLLaMA、skills.sh 生态。

### M5 · 团队版 —— 第 6 周起（等 M4 出现拉动力）

规则同步、基于 `ledger.jsonl` 的报告历史、SSO、审计导出。¥199/499/999。
在约 20 个外部 star 或 3 个团队来问之前不要做。

---

## 3. 决策

| # | 决策 | 结论 |
|---|---|---|
| 1 | 默认因证据太薄而失败？ | **是**（默认 `--fail-on refuted,thin`）。这是差异化点；不喜欢的团队传 `--fail-on refuted`。 |
| 2 | 规则包的事实来源 | `.verdict/rules/` 里的 vendored 文件；registry 推迟到 M5 |
| 3 | `command_succeeds` 白名单 | 内置最小默认 + 团队扩展，绝不自动放行 |
| 4 | 要不要联系上游？ | **暂时不**。发布后再看：等有东西可看时，开一个说明 fork（以及与其 ROADMAP §5 重叠）的 issue 更有价值 |

---

## 4. 风险

| 风险 | 原因 | 缓解 |
|---|---|---|
| 上游做了同样的东西 | reverify ROADMAP §5 写了「走向可验证的编码」 | 他们做行为等价，我们做输出质量（内容、合规、证据）。公开讲清楚 |
| `command_succeeds` 形似 RCE | 从 claim 文件执行命令 | 仅 argv、白名单、无 shell、未列名即 INCONCLUSIVE、cwd 受限、超时 |
| `--min-information` 让团队困惑 | 合适的值依赖规则包规模 | 每次运行都打印数值与阈值；写进 USAGE.md |
| AI 味词表误报 | 「值得注意的是」在普通中文里也会出现 | 规则包可 vendor 可编辑，保守发布，注明是主观判断 |
| 9/25–10/5 带宽低 | 出行 | M3 前重；出行周只做 MCP + SKILL.md + Pages |

---

## 5. 下一步（按顺序）

1. **需要 Kevin（一次性，约 10 分钟）**：在 pypi.org 为 `ai-verdict` 加
   pending trusted publisher，然后 `sh tools/publish.sh`。步骤见
   [RELEASE.md](RELEASE.md)。没有它，action 装不上包。
2. 发布到 Marketplace，并移动浮动 tag `v1`。
3. 出行周（9/25–10/5）：MCP server（`verify_claims`）、skills.sh 的
   `SKILL.md`、GitHub Pages 样例报告。（**已完成**）
4. 然后 M4：`citation_resolves`（**已完成**）、`number_matches_source`、
   词表 v2、首发。

## 6. 自闸（本仓库闸自己）

```bash
verdict check ITERATION-PLAN.md --claims-file .verdict/claims.json --base-dir .
# 19/19 已验证，information 2.413，grounded_score 1.0，exit 0
```

断言：文档、SKILL.md、基准结果、密度预设、提案器、发布前检查与发布脚本都存在；
被跟踪文档里没有密钥形字符串；闸门测试与基准真的跑过。CI
（`.github/workflows/verdict.yml`）里同样执行，包含一个反向测试 —— 脏样例
必须 exit 2。

---

## 7. 重启，2026-11-14

触发原因：闲置 7 周、`verdict-gate` 名字被占、NVIDIA / 阿里 / Cloudflare
进场做验证与质量闸门。

- [x] **改名** `ai-verdict`（pyproject、action、USAGE、RELEASE、计划）。
      仓库仍是 `Roloria/verdict`，CLI 仍是 `verdict`。
- [x] **版本号修复**：`verdict/__init__.py` 0.1.0 → 0.12.0，并由测试断言。
- [x] **`slop_density` 闸门** —— 从 FeedHive 120 条模式（MIT）提炼出 192 个
      可机器判定短语 / 59 个 id，源数据 vendor 在 `tools/vendor/`，带重建脚本。
      按段落统计不同 id 数；单个短语正常，一段命中 `min_hits`（默认 3）才
      REFUTED。
- [x] **`ai-tells-density` 规则包** —— 低误报默认。`ai-tells` v2 保留严格的
      精确短语表并加上密度 claim。
- [x] **`tests_actually_prove` 闸门** —— 删测试、新增 `.skip` / `.only` /
      `@pytest.mark.skip` 标记、改了代码却没动测试，都会亮红旗。迄今最锋利
      的反偷懒检查。
- [x] **`SKILL.md`** —— 仓库根的 Agent Skills 包，供 skills.sh 使用。
- [x] **MCP server** —— `ai-verdict-mcp`，stdio JSON-RPC，工具
      `verify_claims` / `list_rules`，无 SDK 依赖。
- [x] **基准** —— 30 个注入缺陷样例，`eval/run.py` → `eval/RESULTS.md`。
      precision 1.000 / recall 1.000 / F1 1.000，0 漏放、0 误报。定位是回归
      绊线，不是通用准确率声明。
- [x] **Pages workflow** —— 把 `examples/gate.html` 发布为在线样例。
- [x] 自闸扩展到 9 条 claims。

### 当时剩下的（按顺序）

1. **需要 Kevin（约 10 分钟）**：在 PyPI 认领 `ai-verdict`、加 trusted
   publisher、`v0.12.0` tag、Marketplace 发布、移动 `v1`。见 RELEASE.md。
2. `npx skills add Roloria/verdict --skill ai-verdict` —— 验证 skill 能装上
   （仓库已公开）。
3. `citation_resolves` / `number_matches_source` —— 文档垂直场景。
4. 用 demo + 基准数字写首发文章。
5. 团队版 —— 等有拉动力再说。

---

## 8. 融合 open-code-review，2026-11-14

调研了该仓库（1405 个文件，Apache-2.0）的 `internal/agent/selection.go`、
`grouping.go`、`internal/delegate/rulegroup.go`、`.opencodereview/rule.json`
与 `ASSURANCE_CASE.md`。

**借鉴的（仅设计，未复制任何 Apache 代码或数据）**：

| OCR 能力 | verdict 实现 |
|---|---|
| preview 与实跑共享同一次纯前置选择（他们的 #782 漂移 bug） | `scope.build_scope()` —— 单次、确定性决策 |
| 固定顺序的静态门 + 明确的 `ExcludeReason` | `scope.decide()` —— 密钥路径 → 二进制 → 用户规则 → 默认排除 → 已删除 → 过大 |
| 按文件解析规则，按 (source, pattern, text) 分组 | `scope.resolve_rules()` —— 同一三元组键，项目配置在 `.verdict/scope-rules.json` |
| 智能分桶 / i18n 与测试配对，每组 ≤10 文件 | `scope.bundle_changes()` —— 完全确定性，不用 LLM 分组 |
| 委托模式（结构化移交，不调模型） | `verdict scope --delegate` → `verdict-delegate-spec`；agent 一侧已有 MCP |
| 外部定位与反思模块 | `citation_resolves` 闸门 —— 校验文件与行号，返回观测行作证据 |
| 多模式审查（workspace / 分支区间 / commit / 全量扫描） | `scope.collect_changes()` 四种模式；`diff_touches` 增加 `revision` |
| 公开基准的 precision/recall 叙事 | `eval/RESULTS.md` 现在按缺陷类型分解指标 |

**刻意不采纳**：LLM reviewer、provider/model 配置、prompt 模板、token 预算、
session resume、IDE 插件。verdict 的验证路径保持无模型 —— 这是产品的核心约束。

新增/修改文件：`verdict/scope.py`、`verdict/verifier.py`（citation_resolves
+ diff_touches revisions）、`verdict/cli.py`（`verdict scope`）、三个新测试模块、
USAGE / SKILL（两份）/ ATTRIBUTION / 评测结果。

当时测试：**67 个 verdict 测试通过**；基准仍 1.000 / 1.000 / 1.000。

---

## 9. 中英双语支持 + README 重写，2026-11-15

- **i18n 架构**（`verdict/i18n.py`）：语言表、detail 翻译规则、证据字段名映射。
  加一种语言 = 加一份表，调用方无需改动。解析顺序：`--lang` >
  `VERDICT_LANG` > `.verdict/config.json` > `--lang auto`（locale）>
  默认 `zh-CN`。
- **HTML 报告**：单文件内嵌双语，右上角按钮切换（少量内联脚本，无 CDN）。
  服务端 `--lang` 决定打开时显示哪种。`gate.html`（中）与
  `gate.en.html`（英）两份样例。
- **CLI**：全部人类可读文案本地化（标题、标记、汇总、scope、rules、kinds）；
  `--lang` 放在子命令前后都能用。`--json`、协议值、闸门名、claim 文件保持英文。
- **MCP**：`verify_claims` 收 `lang`，在原始值之外返回 `verdict_label` +
  `detail_display`。
- **Action**：新增 `lang` input。
- **README**：重写为中文主版 + 英文版 `README.en.md`，互链切换、当前能力/状态
  表。上游 README 原样归档为 `README.upstream.md`（420 行，未改）。
- `.verdict/config.example.json`、USAGE、两份 SKILL.md 同步更新。
- 测试：76 个 verdict 测试（新增 `test_i18n.py`），覆盖双语报告 + CLI + MCP 切换。

---

## 10. 价值评估 + 采用度工作，2026-11-15

**结论：功能够全面，价值不够。** 价值 ≈ 真实采用 × 可信度，两者此前都接近 0：
0 star、没发布、没有外部用户；手写 30 例基准拿 1.000 说明不了问题；上手要手写
`claims.json`；CI 只会让 build 失败，进不了 code scanning。

**本轮落地（按杠杆排序）**：

| 缺口 | 修法 |
|---|---|
| 可信度 | `eval/calibrate.py` → `eval/CALIBRATION.md`：11 份外部真实 OSS README，运行时拉取（不入库全文），**误报 0/11、注入缺陷检出 22/22** |
| 真实质量缺陷 | 该校准抓出 18 位身份证正则命中 FastAPI / promptfoo README 徽章 URL 的长数字串；在 `secrets-pii` 加边界后重跑两套评测 |
| 上手摩擦 | `verdict init` —— 自动探测 Python/Node/Rust/Go 测试命令，生成 `.verdict/` 配置 + claims + 白名单 + 范围规则 + GitHub Actions workflow + pre-commit 脚本，未经 `--force` 不覆盖 |
| CI/审计深度 | `--sarif` → 带 `partialFingerprints` 的 SARIF 2.1.0，仅 REFUTED/INCONCLUSIVE 成为 finding；`init` 生成的 workflow 负责上传 |

测试：**85 个 verdict 测试**（`test_init_sarif.py`、`test_i18n.py`），自闸双语
12/12，基准不变。

**当时剩下的（按杠杆排序）**：

| # | 任务 | 为什么 |
|---|---|---|
| P0 | 发布（需 Kevin）：PyPI trusted publisher → `v0.12.0` → Marketplace | `pip install ai-verdict` 能用之前，其它都不复利 |
| P0 | `verdict propose` —— 从产物确定性抽取可验证断言（数字、路径、API 名、命令输出）生成 claims 草稿 | 补齐 reverify 协议缺的另一半：agent 只能**提出** claim，不能裁决。干掉手写 claims.json 的摩擦 |
| P1 | PR annotation + diff-only（只查新增行） | 不被历史债务卡住，成熟仓库也能用 |
| P1 | `verdict ledger` 查询 + 审计导出 | 把 `.verdict/ledger.jsonl` 从日志变成团队愿意付费的资产 |
| P2 | 团队版：私有规则同步、报告历史、SSO | 等 P0/P1 出现拉动力 |

---

## 11. P0 迭代，2026-11-15 04:00

**P0 #2 `verdict propose` —— 完成。** 补齐 reverify「模型提出，工具裁决」协议
缺的另一半：claim 文件不必再手写。纯确定性抽取（无 LLM / 网络 / 文件读取），
只有能绑定**外部证据**的断言才会变成 claim：

| 产物里的 | 生成的 claim |
|---|---|
| `src/app.py:12` | 带显式 citations 的 `citation_resolves` |
| `README.md` | `file_exists` |
| `` `pytest -q` ``（白名单内） | `command_succeeds` |
| 「all tests pass」 | `tests_actually_prove` |
| 「no secrets」 | `text_absent`（凭据形状） |

数字、百分比、URL **故意跳过**并记在 `skipped` 里：断言一份文档含有它自己的
数字是自证循环。`--out` 写出的 claims.json 可直接被 `verdict check` 消费。
同一输入永远得到同一份草稿。

**P0 #1 发布 —— 能自动化的都做完了**：
- 通过 API 建好 GitHub `pypi` 环境（无需 secret，OIDC）。
- `verdict release-check`：检查包名、版本同步、workflow、action、本地 tag、
  构建后端、PyPI 状态与环境。自检后 7✓/1✗（仅缺 tag）。
- `tools/publish.sh`：一键 tag+push；拒绝脏工作区、幂等、不 force push。
- 装好 `build`，本地 wheel 路径可校验。
- RELEASE.md 重写为：`verdict release-check` → pypi.org 点一次 →
  `sh tools/publish.sh` → Marketplace。

**仍需 Kevin（本机无法代做）**：在
https://pypi.org/manage/account/publishing/ 为 `ai-verdict` 添加 *pending
trusted publisher*（Roloria / verdict / publish-pypi.yml / pypi）。**没有推
`v0.12.0` tag**：publisher 没配，打 tag 只会让发布 workflow 失败。他配好后
跑 `sh tools/publish.sh` 即可完成发布。

测试：**92 个 verdict 测试**，自闸扩展，基准与校准不变。

**发布之后**：PR annotation + diff-only、`verdict ledger` 查询/审计导出、团队版。

---

## 12. 计划文档双语化，2026-11-15 04:46

中文成为主版（本文件），英文原版归档为
[ITERATION-PLAN.en.md](ITERATION-PLAN.en.md)，与 README 的双版约定一致；
两版顶部互链。`README.en.md` 的文档链接改指英文版。自闸 target 仍是本文件。

---

## 13. 自检迭代，2026-11-15 05:00

跑了一轮全量自检：测试套件、自闸（中英两种语言）、7 个子命令 smoke、Markdown
链接、11 个 YAML、`python -m build --wheel` 与 wheel 内容清单。发现并修掉 4 个
真实缺陷：

| 缺陷 | 修法 |
|---|---|
| `verdict report` 传入 claims 数组时抛 AttributeError | 校验运行报告 JSON 结构，给双语友好错误 |
| `verdict init` 生成的 workflow 上传不存在的 SARIF 文件 | check 步骤加 `--sarif verdict.sarif` |
| `release.py` 硬编码 Roloria/verdict、把「PyPI 名字空闲」误报为 ✗、只检查 `build` 模块 | 从 git remote 推导 slug；空闲名字/离线作为信息项；构建检查补 setuptools + wheel |
| SARIF finding 行号恒为 1 | 从 evidence 的命中偏移（或引用失败的行号）换算真实行号 |

另：本地 venv 补装 setuptools/wheel，wheel 构建成功（87 个文件，新增模块与数据
全部入包）；`verdict release-check` 从 6✓/2✗ 变为 7✓/1✗。新增 8 个回归测试
（`test_selfcheck_fixes.py`）。
