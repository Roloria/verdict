# Usage

```bash
pip install ai-verdict            # from PyPI
# or, from a checkout:
pip install -e ".[dev]"
pytest verdict/tests reverify/tests -q     # 345 passed, 55 skipped
```

## 1. Gate one artifact against a claim file

```bash
verdict check report.md --claims-file claims.json --base-dir .
```

`claims.json` is a list of claims. Flat form is fine — every key that is not
`kind` / `id` / `note` / `depends_on` / `observe` becomes a parameter:

```json
[
  {"kind": "text_present", "value": "31 files", "note": "the number must be real"},
  {"kind": "text_absent",  "pattern": "sk-[A-Za-z0-9]{20,}", "regex": true},
  {"kind": "file_exists",  "path": "src/app.py", "min_bytes": 10},
  {"kind": "command_succeeds", "argv": ["pytest", "-q"], "timeout": 300},
  {"kind": "diff_touches", "paths": ["src/app.py"], "base": "origin/main"},
  {"kind": "slop_density", "preset": "slop-120", "min_hits": 3},
  {"kind": "tests_actually_prove", "base": "origin/main"}
]
```

## 2. Gate against a rule bundle

```bash
verdict rules list                                  # what is available
verdict check report.md --rules ai-tells,secrets-pii --report gate.html
verdict rules add ./our-house-style.json            # vendor a team bundle
```

Bundles resolve in this order: `.verdict/rules/<name>.json` (yours, wins) →
built-ins in `verdict/rules/` → a literal file path. A bundle may override
weights:

```json
{"name": "house-style", "weights": {"text_absent": 0.5},
 "claims": [{"kind": "text_absent", "value": "synergy"}]}
```

Shipped bundles:

| bundle | content | false positives |
|---|---|---|
| `ai-tells` v2 | 24 exact phrases (EN+ZH) + `slop_density` | higher — strict house style |
| `ai-tells-density` | 192 machine-checkable phrases from 59 catalogued patterns, counted per paragraph | low — use this by default |
| `secrets-pii` | 9 credential / identifier regexes | low |
| `pr-evidence` | tests ran, no placeholders | low |

The density preset is derived from FeedHive/ai-slop-detector (MIT, 120 patterns);
`tools/vendor/` keeps the original catalogue and `tools/build_slop_patterns.py`
regenerates the data. Only phrases a deterministic checker can match are kept.

## 3. In CI

```yaml
- uses: Roloria/verdict@v1
  with:
    target: docs/report.md
    rules: ai-tells,secrets-pii
    min-information: "2"          # bundles land near 2.5; tune to your rule count
    report: gate.html             # optional
```

Outputs: `exit-code`, `information`, `grounded`. The run is also written to the
job summary as a table.

Or plain CLI:

```yaml
- run: pipx install ai-verdict
- run: verdict check report.md --rules ai-tells,secrets-pii --base-dir .
```

Exit codes:

| code | meaning |
|---|---|
| 0 | grounded: nothing refuted and the evidence is thick enough |
| 2 | a claim was REFUTED or INVALIDATED |
| 3 | nothing refuted, but the verified set is too thin (`--min-information`) |
| 4 | something was INCONCLUSIVE (`--strict`, or `--fail-on inconclusive`) |

`--fail-on refuted,thin,inconclusive` picks which of those break the build
(default `refuted,thin`).

## Gates

| kind | asserts | key params |
|---|---|---|
| `text_present` | output contains a literal or regex | `value` / `pattern`+`regex`, `count`, `min_count`, `max_count` |
| `text_absent` | output does **not** contain it | same |
| `file_exists` | a repo-relative path exists | `path`, `min_bytes` |
| `command_succeeds` | an allow-listed command exits as expected | `argv` (list, no shell), `cwd`, `timeout`, `expect_exit`, `expect_stdout` |
| `diff_touches` | the git diff touches the claimed paths | `paths`, `base`, `mode` (`all`/`any`), `revision` (`base`/`workspace`/`merge-base`/`commit`) |
| `citation_resolves` | every `path:line` reference really resolves | `from_text`, `citations`, `contains`, `max_citations` |
| `slop_density` | no paragraph hits N **distinct** AI-tell patterns | `preset: slop-120`, `min_hits`, or custom `patterns` |
| `tests_actually_prove` | tests were not deleted / skipped / left untouched | `base`, `require_test_change`, `test_globs` |

Plus every reverify kind (`bytes_at`, `string_present`, `functions_equiv`, ...).

## Review scope (deterministic pre-dispatch)

Adapted from open-code-review's engineering layer. One pure selection pass is
shared by preview and real runs, so they cannot disagree.

```bash
verdict scope --mode workspace --json
verdict scope --mode merge-base --base main --to HEAD --json
verdict scope --mode commit --commit abc123 --delegate --json
```

Modes: `workspace` (staged + unstaged + untracked), `merge-base`, `commit`,
`base` (plain `git diff <ref>`).

Output contains:

| field | meaning |
|---|---|
| `decisions` | every changed file with an explicit reason: `secret-path` / `binary` / `user-exclude` / `default-exclude` / `deleted` / `too-large` / `ok` |
| `selected` | files worth attention after static gates |
| `rule_groups` | files grouped by `(source, pattern, rules)` — provenance is exact for every member |
| `bundles` | implementation paired with its tests, i18n siblings paired, rest grouped by directory, ≤10 files |
| `--delegate` | a structured spec for a host agent; verdict calls no model |

Per-file rule resolution (optional `.verdict/scope-rules.json`):

```json
{"rules": [{"pattern": "src/**/*.py", "rules": ["house-style", "secrets-pii"]}]}
```

Unmatched files fall back to rules by extension. `--exclude GLOB` adds a
user-level gate. Secret paths are excluded first and cannot be readmitted.

`citation_resolves` is the location/reflection check: it extracts `path:line`
references from a report, verifies the file and line, and returns the observed
line as evidence. Bad line numbers or missing files are REFUTED.

## Safety: `command_succeeds`

- argv only; a string `argv` is rejected with "no shell strings".
- Default allowlist: `pytest`, `python -m pytest`, `node --check`, `npx tsc`,
  `tsc --noEmit`, `eslint`, `ruff`, `git diff` (argv prefix match).
- Anything unlisted is **INCONCLUSIVE and never executed**. Extend with
  `.verdict/allowlist.json`:

```json
{"allow": [["pytest"], ["npm", "test"], ["go", "test", "./..."]]}
```

- `cwd` must resolve inside `--base-dir`; a `cwd` that escapes is REFUTED.

## Scoring, and why

Two numbers, both in every report:

- **information** — sum of the weights of the VERIFIED claims. This is what
  `--min-information` gates on.
- **grounded_score** — information / total weight of everything scored.

Repeated claims of the same kind decay harmonically (the Nth one counts 1/N).
Without that, a 33-claim bundle where everything passes scores 19 and the
"thin evidence" gate can never fire — the exact gaming the metric exists to
stop. With it, the same run scores 2.5, and a clean vs dirty artifact reads
1.0 vs 0.53 on grounded_score.

REFUTED claims keep their full weight: a failure should read as "this rule
matters", not as a small number.

## Ledger and report

- Every run appends one JSON line to `.verdict/ledger.jsonl` (`--no-ledger` to
  skip). That file is the asset a team eventually pays to keep and audit.
- `--report gate.html` writes a single-file **Chinese** HTML report — no CDN, no
  JS dependencies. `verdict report run.json --out gate.html` re-renders a saved
  run. Only the presentation layer is translated: verdict values and `--json`
  output stay English for CI and scripts.

## Claim 提案（补齐协议的另一半）

```bash
verdict propose report.md --out claims.json
verdict check report.md --claims-file claims.json
```

`propose` 是确定性抽取器（无 LLM、无网络、无文件读取），只把**能绑定外部证据**
的句子变成 claim：`path:line` → `citation_resolves`、文件路径 → `file_exists`、
白名单命令 → `command_succeeds`、"tests pass" → `tests_actually_prove`、
"no secrets" → `text_absent`。

数字 / 百分比 / URL 会被**跳过**并记录原因：断言一份文档含有它自己的数字是
自证循环，没有外部证据；需要人工绑定源文件（未来的 `number_matches_source`）。
草稿不是结论，跑 `verdict check` 才算数。

## 发布前检查

```bash
verdict release-check          # 检查包名/版本/workflow/tag/PyPI/environment
sh tools/publish.sh            # 配好 trusted publisher 后一键打 tag 发布
```

`release-check` 会列出剩余动作；`publish.sh` 拒绝脏工作区、可重复运行、不 force
push。详见 RELEASE.md。

## 零配置起步

```bash
cd any-repo
verdict init                  # 生成 .verdict/ 配置、GitHub Actions workflow、pre-commit 脚本
verdict check README.md --claims-file .verdict/claims.json
```

`init` 自动探测测试框架（Python / Node / Rust / Go），把测试命令写进 claims 和
白名单；默认不覆盖已有文件，`--force` 才覆盖。不改动 `.git/`，钩子脚本放在
`.verdict/pre-commit.sh` 由你自行安装。

## CI / 审计输出

```bash
verdict check report.md --claims-file claims.json --sarif findings.sarif
```

SARIF 2.1.0：仅 `REFUTED`（error）与 `INCONCLUSIVE`（warning）成为 finding，
带 `partialFingerprints` 去重和证据摘要；`github/codeql-action/upload-sarif`
可直接上传。`init` 生成的 workflow 已包含上传步骤。

## 校准 / 可信度

```bash
python eval/run.py          # 30 例回归绊线 → eval/RESULTS.md
python eval/calibrate.py    # 11 份外部真实 README → eval/CALIBRATION.md
```

校准脚本运行时下载外部文档并缓存到 `eval/.cache/`（gitignored），不把第三方
全文提交进仓库；离线时复用缓存。它同时测量真实文档上的误报率与注入缺陷的
检出率。当前结果：误报 0/11，注入检出 22/22。

## 语言切换 / Language

`zh-CN` 和 `en` 都支持。新增一种语言只需在 `verdict/i18n.py` 加一份消息表、
一组 detail 翻译规则和一份证据字段名映射，调用方无需改动。

```bash
verdict check report.md --rules ai-tells-density --lang zh-CN
verdict --lang en check report.md --rules ai-tells-density
VERDICT_LANG=en verdict rules list
verdict check ... --lang auto          # 跟随 LC_ALL / LANG
```

优先级：`--lang` > `VERDICT_LANG` > `.verdict/config.json`（示例
`.verdict/config.example.json`）> 默认 `zh-CN`。

HTML 报告是**单文件双语**：两种语言都内嵌在页面里，右上角按钮即时切换，
离线打开也能切。`--lang` 决定打开时显示哪种。

保持英文的部分：协议值 `VERIFIED/REFUTED/...`、gate 名、`--json` 输出、
证据字段名（JSON）、claim 文件。CI 与脚本不受语言影响。

## Agent surfaces

`SKILL.md` at the repo root is an Agent Skills bundle: an agent can install it
and gate its own output before reporting done.

```bash
npx skills add Roloria/verdict --skill ai-verdict
# or manually:
mkdir -p ~/.claude/skills/ai-verdict
cp skills/ai-verdict/SKILL.md ~/.claude/skills/ai-verdict/SKILL.md
```

Both copies (`SKILL.md` at root and `skills/ai-verdict/SKILL.md`) are asserted
identical by the test suite, so the single-file and skills.sh installs agree.

MCP server over stdio (no SDK dependency), two tools: `verify_claims` and
`list_rules`.

```bash
ai-verdict-mcp
# {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"verify_claims",
#  "arguments":{"text":"...","rules":"ai-tells-density,secrets-pii"}}}
```

## Benchmark and self-gate

```bash
python eval/run.py          # 30 injected-defect cases → eval/RESULTS.md
verdict check ITERATION-PLAN.md --claims-file .verdict/claims.json
```

The self-gate asserts the docs exist, no key-shaped strings are tracked, the
gate suite passes and the benchmark stays green. CI runs it on every push,
including a negative test that the sloppy example must exit 2.
