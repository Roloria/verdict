"""Language support for verdict.

Add a language by adding one entry to MESSAGES, one DETAIL_RULES list and one
EVIDENCE_KEYS map — no caller needs to change.

Resolution order (highest wins):
  1. --lang / explicit argument
  2. VERDICT_LANG environment variable
  3. .verdict/config.json  ->  {"lang": "zh-CN"}
  4. locale (LC_ALL / LANG) when lang=auto
  5. DEFAULT_LANG

Protocol values (VERIFIED / REFUTED / ...), claim kinds, evidence field names in
JSON and the --json output are NEVER translated. Only human-facing prose is.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

LANGS = ("zh-CN", "en")
DEFAULT_LANG = "zh-CN"
_ALIASES = {
    "zh": "zh-CN", "zh-cn": "zh-CN", "zh_cn": "zh-CN", "cn": "zh-CN", "chinese": "zh-CN",
    "en": "en", "en-us": "en", "en_us": "en", "us": "en", "english": "en",
}

MESSAGES: Dict[str, Dict[str, str]] = {
    "report.title": {"zh-CN": "verdict · 输出质量闸门报告", "en": "verdict · gate report"},
    "report.artifact": {"zh-CN": "产物", "en": "artifact"},
    "report.rules": {"zh-CN": "规则包：{rules}", "en": "rules: {rules}"},
    "report.lang_switch": {"zh-CN": "English", "en": "中文"},
    "card.verified": {"zh-CN": "已验证", "en": "verified"},
    "card.refuted": {"zh-CN": "已驳回", "en": "refuted"},
    "card.inconclusive": {"zh-CN": "未定论", "en": "inconclusive"},
    "card.information": {"zh-CN": "信息量", "en": "information"},
    "card.grounded_score": {"zh-CN": "证据覆盖度", "en": "grounded score"},
    "card.gate": {"zh-CN": "闸门结论", "en": "gate"},
    "gate.pass": {"zh-CN": "通过", "en": "GROUNDED"},
    "gate.fail": {"zh-CN": "未通过", "en": "NOT GROUNDED"},
    "table.verdict": {"zh-CN": "结论", "en": "verdict"},
    "table.gate": {"zh-CN": "闸门", "en": "gate"},
    "table.weight": {"zh-CN": "权重", "en": "weight"},
    "table.claim": {"zh-CN": "断言", "en": "claim"},
    "footer.replay": {"zh-CN": "复现命令：", "en": "replay:"},
    "footer.sha": {"zh-CN": "产物 SHA-256：", "en": "artifact sha256:"},
    "footer.version": {"zh-CN": "verdict {version} · Python {python}", "en": "verdict {version} · python {python}"},
    "badge.VERIFIED": {"zh-CN": "已验证", "en": "VERIFIED"},
    "badge.REFUTED": {"zh-CN": "已驳回", "en": "REFUTED"},
    "badge.INCONCLUSIVE": {"zh-CN": "未定论", "en": "INCONCLUSIVE"},
    "badge.OBSERVED": {"zh-CN": "已观察", "en": "OBSERVED"},
    "badge.INVALIDATED": {"zh-CN": "已失效", "en": "INVALIDATED"},
    "mark.VERIFIED": {"zh-CN": "通过", "en": "PASS"},
    "mark.REFUTED": {"zh-CN": "失败", "en": "FAIL"},
    "mark.INCONCLUSIVE": {"zh-CN": "未定", "en": "????"},
    "mark.OBSERVED": {"zh-CN": "观察", "en": "note"},
    "mark.INVALIDATED": {"zh-CN": "跳过", "en": "skip"},
    "cli.header": {"zh-CN": "=== verdict · AI 输出质量闸门 ===", "en": "=== verdict: AI output gate ==="},
    "cli.hidden": {
        "zh-CN": "（另有 {n} 条通过的断言已隐藏，--verbose 查看全部）",
        "en": "(+{n} passing claim(s) hidden, --verbose lists them)",
    },
    "cli.summary": {
        "zh-CN": "已验证 {verified}/{total}（已驳回 {refuted}，未定论 {inconclusive}，已失效 {invalidated}）",
        "en": "verified {verified}/{total} (refuted {refuted}, inconclusive {inconclusive}, invalidated {invalidated})",
    },
    "cli.info": {
        "zh-CN": "信息量 {information} / 最低 {minimum}   证据覆盖度 {score}",
        "en": "information {information} / min {minimum}   grounded_score {score}",
    },
    "cli.flags": {
        "zh-CN": "可信 {trustworthy}  证据充足 {informative}  闸门 {gate}",
        "en": "trustworthy {trustworthy}  informative {informative}  {gate}",
    },
    "cli.gate_kinds": {"zh-CN": "闸门类型：{kinds}", "en": "gate kinds: {kinds}"},
    "cli.report": {"zh-CN": "报告：{path}", "en": "report: {path}"},
    "scope.summary": {
        "zh-CN": "模式={mode} 变更={changed} 入选={selected} 排除={excluded} 分桶={bundles}",
        "en": "mode={mode} changed={changed} selected={selected} excluded={excluded} bundles={bundles}",
    },
    "scope.excluded": {"zh-CN": "  排除 {path}：{reason}", "en": "  excluded {path}: {reason}"},
    "scope.hint": {
        "zh-CN": "（--json 查看完整范围 / --delegate 输出 agent 移交说明）",
        "en": "(--json for the full structured scope / --delegate for an agent hand-off)",
    },
    "rules.none": {"zh-CN": "未找到规则包", "en": "no bundles found"},
    "rules.vendored": {"zh-CN": "已存入 -> {path}", "en": "vendored -> {path}"},
    "kinds.title": {"zh-CN": "verdict 闸门类型：", "en": "verdict gate kinds:"},
    "kinds.upstream": {
        "zh-CN": "\n另有全部 reverify 类型（bytes_at、string_present、functions_equiv ...）",
        "en": "\nplus every reverify kind (bytes_at, string_present, functions_equiv, ...)",
    },
    "init.created": {"zh-CN": "已生成 {path}", "en": "created {path}"},
    "init.skipped": {"zh-CN": "跳过（已存在）{path}", "en": "skipped (exists) {path}"},
    "init.detected": {"zh-CN": "检测到测试命令：{command}", "en": "detected test command: {command}"},
    "init.next": {"zh-CN": "下一步：{first}", "en": "next: {first}"},
    "cli.sarif": {"zh-CN": "SARIF：{path}", "en": "SARIF: {path}"},
    "bool.yes": {"zh-CN": "是", "en": "true"},
    "bool.no": {"zh-CN": "否", "en": "false"},
}

EVIDENCE_KEYS: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "occurrences": "出现次数", "at": "位置", "bytes": "字节数", "exit_code": "退出码",
        "duration_ms": "耗时(ms)", "stdout_sha256": "输出哈希", "matched": "已命中",
        "missing": "缺失", "changed_count": "变更数", "resolved": "已解析",
        "allowlisted": "白名单", "encoding": "编码", "needle": "匹配串",
        "regex": "正则", "length": "长度", "path": "路径",
    },
    "en": {},
}

# Human-facing gate details are English in the core (they are data, not UI).
# Translate per language; unmatched text passes through unchanged.
DETAIL_RULES: Dict[str, List[Tuple[str, str]]] = {
    "zh-CN": [
        (r"unknown claim kind '(.+)'", r"未知的闸门类型「\1」"),
        (r"malformed claim: (.+)", r"断言格式错误：\1"),
        (r"tool error: (.+)", r"工具错误：\1"),
        (r"found (\d+) occurrence\(s\) that must not be there", r"出现 \1 处本不该出现的内容"),
        (r"absent as claimed", r"符合断言：未出现"),
        (r"not found in the output", r"产物中未找到"),
        (r"found (\d+), claim needs at least (\d+)", r"出现 \1 次，断言要求至少 \2 次"),
        (r"found (\d+), claim allows at most (\d+)", r"出现 \1 次，断言上限为 \2 次"),
        (r"found (\d+), within the claimed range", r"出现 \1 次，在断言范围内"),
        (r"^found$", r"已找到"),
        (r"path escapes the repository root(?: \(or is the root itself\))?", r"路径越出仓库根目录"),
        (r"path does not exist or is not a file", r"路径不存在或不是文件"),
        (r"file is (\d+) bytes, claim needs at least (\d+)", r"文件仅 \1 字节，断言要求至少 \2 字节"),
        (r"exists \((\d+) bytes\)", r"文件存在（\1 字节）"),
        (r"cwd escapes the repository root", r"工作目录越出仓库根目录"),
        (r"cwd is not a directory", r"工作目录不是文件夹"),
        (r"command is not allow-listed; refusing to execute.*", r"命令不在白名单，拒绝执行（请加入 .verdict/allowlist.json）"),
        (r"'(.+)' is not on PATH", r"在 PATH 中找不到 \1"),
        (r"timed out after (.+)s", r"执行超时（\1 秒）"),
        (r"could not execute: (.+)", r"无法执行：\1"),
        (r"exit (\d+), expected (\d+)", r"退出码 \1，预期 \2"),
        (r"stdout does not match /(.+)/", r"标准输出不匹配 /\1/"),
        (r"exit (\d+) in (\d+)ms", r"退出码 \1，耗时 \2 毫秒"),
        (r"git is not available", r"git 不可用"),
        (r"git diff failed: (.+)", r"git diff 失败：\1"),
        (r"git diff failed(?: \(not a repo, or bad base\?\))?", r"git diff 失败（不是仓库或基准无效？）"),
        (r"diff touches (\d+) of the claimed paths", r"差异触及 \1 个声明的路径"),
        (r"diff touches none of the claimed paths", r"差异未触及任何声明的路径"),
        (r"claimed paths absent from the diff: (.+)", r"差异中缺少声明的路径：\1"),
        (r"diff touches all (\d+) claimed path\(s\)", r"差异触及全部 \1 个声明路径"),
        (r"(\d+) distinct AI-tell patterns in one paragraph \(limit (\d+)\)", r"单段命中 \1 个不同 AI 味模式（阈值 \2）"),
        (r"max (\d+) distinct patterns in a paragraph, below (\d+)", r"单段最多命中 \1 个模式，低于阈值 \2"),
        (r"nothing changed against the base ref", r"与基准相比没有任何改动"),
        (r"deleted test file\(s\): (.+)", r"删除了测试文件：\1"),
        (r"(\d+) new skip/\.only marker\(s\) in the diff", r"差异中新增 \1 处跳过/仅运行标记"),
        (r"code changed with no test file changed", r"修改了代码但没有任何测试文件变动"),
        (r"(\d+) test file\(s\) changed, no tampering markers", r"\1 个测试文件有变动，未发现篡改标记"),
        (r"no path:line citations found in the output", r"产物中未发现 path:line 形式的引用"),
        (r"(\d+) of (\d+) cited location\(s\) do not resolve", r"\2 处引用中有 \1 处无效"),
        (r"all (\d+) cited location\(s\) resolve with observed line content", r"\1 处引用均有效，已返回实际行内容"),
        (r"escapes the repository root", r"越出仓库根目录"),
        (r"file not found", r"文件不存在"),
        (r"line out of range \(file has (\d+) lines\)", r"行号越界（文件共 \1 行）"),
        (r"line content mismatch", r"行内容与断言不符"),
    ],
    "en": [],
}
_COMPILED = {
    lang: [(re.compile(p), r) for p, r in rules]
    for lang, rules in DETAIL_RULES.items()
}

_current_lang: Optional[str] = None


def normalize(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = str(value).strip().lower().replace("_", "-")
    if key == "auto":
        return "auto"
    return _ALIASES.get(key, key if key in LANGS else None)


def from_locale() -> str:
    loc = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    return "zh-CN" if loc.startswith("zh") else "en"


def resolve(explicit: Optional[str] = None, base_dir: str = ".") -> str:
    """Pick a language. `explicit` wins; config and env come next."""
    for candidate in (explicit, os.environ.get("VERDICT_LANG")):
        norm = normalize(candidate)
        if norm == "auto":
            return from_locale()
        if norm:
            return norm
    cfg = os.path.join(base_dir, ".verdict", "config.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                norm = normalize(json.load(f).get("lang"))
            if norm == "auto":
                return from_locale()
            if norm:
                return norm
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return DEFAULT_LANG


def set_lang(lang: Optional[str] = None, base_dir: str = ".") -> str:
    global _current_lang
    _current_lang = resolve(lang, base_dir)
    return _current_lang


def get_lang() -> str:
    return _current_lang or set_lang()


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    lang = lang or get_lang()
    template = MESSAGES.get(key, {}).get(lang) or MESSAGES.get(key, {}).get(DEFAULT_LANG) or key
    return template.format(**kwargs) if kwargs else template


def verdict_label(verdict: str, lang: Optional[str] = None) -> str:
    return t(f"badge.{verdict}", lang) if f"badge.{verdict}" in MESSAGES else verdict


def mark_label(verdict: str, lang: Optional[str] = None) -> str:
    return t(f"mark.{verdict}", lang) if f"mark.{verdict}" in MESSAGES else verdict


def translate_detail(detail: Any, lang: Optional[str] = None) -> str:
    lang = lang or get_lang()
    rules = _COMPILED.get(lang, [])

    def one(segment: str) -> str:
        for pattern, repl in rules:
            m = pattern.match(segment)
            if m:
                return m.expand(repl)
        return segment

    joiner = "；" if lang == "zh-CN" else "; "
    return joiner.join(one(part) for part in str(detail or "").split("; "))


def evidence_line(ev: Any, lang: Optional[str] = None, show: Sequence[str] = ()) -> str:
    lang = lang or get_lang()
    keys = EVIDENCE_KEYS.get(lang, {})
    if not isinstance(ev, dict):
        return ""
    parts = []
    for k in show:
        if k not in ev:
            continue
        v = ev[k]
        if isinstance(v, bool):
            v = t("bool.yes" if v else "bool.no", lang)
        elif isinstance(v, list):
            if not v:
                continue
            v = ", ".join(str(x) for x in v[:8]) + (" ..." if len(v) > 8 else "")
        elif isinstance(v, str) and len(v) > 60:
            v = v[:57] + "..."
        parts.append(f"{keys.get(k, k)}={v}")
    return "  ".join(parts)
