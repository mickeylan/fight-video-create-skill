#!/usr/bin/env python3
"""明文资料库的确定性检索与正文读取入口。"""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAIN_DIR = ROOT / "data" / "plain"
SCOPES = ("scenes", "design", "moves", "skills", "scripts")

_config = json.loads((PLAIN_DIR / "router_config.json").read_text(encoding="utf-8"))
WEIGHTS = _config["weights"]
WEAK_MIN_LEN = int(_config["weak_min_len"])
WEAK_TERMS = frozenset(_config["weak_terms"])
_indexes = {}
_contents = {}
_ascii_patterns = {}


def _load_data():
    """启动时一次性载入索引和正文，查询过程不再执行磁盘 I/O。"""
    for scope in SCOPES:
        scope_dir = PLAIN_DIR / scope
        index_doc = json.loads((scope_dir / "_index.json").read_text(encoding="utf-8"))
        items = {}
        for item in index_doc.get("available", []):
            item_id = str(item.get("id", ""))
            if not item_id:
                continue
            meta = dict(item)
            meta_path = scope_dir / f"{item_id}.meta.json"
            if meta_path.is_file():
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            items[item_id] = meta

            content = None
            for extension in (".txt", ".md"):
                body_path = scope_dir / f"{item_id}{extension}"
                if body_path.is_file():
                    content = body_path.read_text(encoding="utf-8")
                    break
            _contents[(scope, item_id)] = content

        _indexes[scope] = {
            "items": items,
            "routing_rules": index_doc.get("routing_rules", []),
            "conflict_resolution": index_doc.get("conflict_resolution", []),
        }


_load_data()


def _compact(value):
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def _fold(value):
    return unicodedata.normalize("NFKC", str(value)).casefold()


def _ascii_pattern(keyword):
    pattern = _ascii_patterns.get(keyword)
    if pattern is None:
        pattern = re.compile(rf"(?<![a-z]){re.escape(keyword)}s?(?![a-z])")
        _ascii_patterns[keyword] = pattern
    return pattern


def _keyword_matches(keyword, compact_query, folded_query):
    if not keyword.isascii():
        return keyword in compact_query
    pattern = _ascii_pattern(keyword)
    return bool(pattern.search(folded_query) or pattern.search(compact_query))


def _matched_keywords(query, keywords):
    compact_query = _compact(query)
    if not compact_query:
        return []
    folded_query = _fold(query)
    matched = []
    seen = set()
    for raw_keyword in keywords:
        keyword = _compact(raw_keyword)
        if not keyword or keyword in seen:
            continue
        if _keyword_matches(keyword, compact_query, folded_query):
            matched.append(str(raw_keyword))
            seen.add(keyword)
    return matched


def _is_short(keyword):
    return len(_compact(keyword)) < WEAK_MIN_LEN


def _is_weak(keyword):
    return _compact(keyword) in WEAK_TERMS


def _has_strong_keyword(keywords):
    return any(not _is_short(keyword) and not _is_weak(keyword) for keyword in keywords)


def _has_multi_character_keyword(keywords):
    return any(not _is_short(keyword) for keyword in keywords)


def _score(scope, query, item):
    field_hits = {}
    unique_scores = {}
    weighted_score = 0
    for field, weight in WEIGHTS[scope].items():
        matches = _matched_keywords(query, item.get(field, []))
        if not matches:
            continue
        field_hits[field] = matches
        weighted_score += len(matches) * weight
        for keyword in matches:
            unique_scores.setdefault(_compact(keyword), weight)

    candidate = {
        "id": item.get("id"),
        "file": item.get("file"),
        "name": item.get("name") or Path(str(item.get("file", ""))).stem,
        "hit_count": len(unique_scores),
        "weighted_score": weighted_score,
        "field_hits": field_hits,
        "matched_keywords": [keyword for values in field_hits.values() for keyword in values],
        "retrieval_hint": item.get("retrieval_hint", ""),
        "avoid_when": item.get("avoid_when", []),
    }
    if scope == "skills":
        candidate["showcase"] = item.get("showcase", "")
        candidate["selection_notice"] = {
            "secondary_keywords": item.get("secondary_keywords", []),
            "condition_prompt": item.get("condition_prompt", ""),
            "condition_options": item.get("condition_options", []),
            "move_library_exclusions": item.get("move_library_exclusions", []),
        }
    elif item.get("showcase"):
        candidate["showcase"] = item["showcase"]
    return candidate


def _available(scope):
    result = []
    for item in _indexes.get(scope, {}).get("items", {}).values():
        result.append({
            "id": item.get("id"),
            "file": item.get("file"),
            "name": item.get("name") or Path(str(item.get("file", ""))).stem,
            "showcase": item.get("showcase", ""),
            "retrieval_hint": item.get("retrieval_hint", ""),
        })
    return result


def _match(query, scope):
    index = _indexes.get(scope)
    if index is None:
        return {
            "scope": scope, "query": query, "match_rule": "未知 scope", "primary": None,
            "eligible": [], "weak_fallback": False, "available": [],
            "routing_rules": [], "conflict_resolution": [],
        }

    scored = [_score(scope, query, item) for item in index["items"].values()]
    matched = [candidate for candidate in scored if candidate["hit_count"] >= 1]
    strong = [candidate for candidate in matched if _has_strong_keyword(candidate["matched_keywords"])]
    if strong:
        eligible = strong
        weak_fallback = False
    else:
        eligible = [candidate for candidate in matched if _has_multi_character_keyword(candidate["matched_keywords"])] or matched
        weak_fallback = bool(matched)

    eligible.sort(key=lambda item: (-item["hit_count"], -item["weighted_score"], str(item["id"])))
    match_rule = (
        "仅按单体、群体或 buff 范围召回候选；不自动指定主技能；二级条件不参与匹配"
        if scope == "skills"
        else "至少命中一个路由关键词；先按唯一命中数、再按字段权重排序；只命中单字或高频通用词的候选在存在更强命中时让位，全库无更强命中时回退使用"
    )
    return {
        "scope": scope,
        "query": query,
        "match_rule": match_rule,
        "primary": None if scope == "skills" else eligible[0] if eligible else None,
        "eligible": eligible,
        "weak_fallback": weak_fallback,
        "available": _available(scope),
        "routing_rules": list(index["routing_rules"]),
        "conflict_resolution": list(index["conflict_resolution"]),
    }


def _resolve_item(scope, value):
    items = _indexes.get(scope, {}).get("items", {})
    if value in items:
        return value
    normalized = value.replace("\\", "/").rsplit("/", 1)[-1]
    for item_id, item in items.items():
        file_name = str(item.get("file", ""))
        if normalized == file_name or normalized == file_name.replace("\\", "/").rsplit("/", 1)[-1]:
            return item_id
    return None


def _read(path):
    normalized = str(path).strip().replace("\\", "/")
    if "/" not in normalized:
        for scope in SCOPES:
            item_id = _resolve_item(scope, normalized)
            if item_id is not None:
                return _contents[(scope, item_id)], None
        return None, f"未找到 {path}"
    scope, value = normalized.split("/", 1)
    if scope not in SCOPES or not value or "/" in value:
        return None, f"无效路径: {path}"
    item_id = _resolve_item(scope, value)
    if item_id is None:
        return None, f"未找到 {scope}/{value}"
    content = _contents.get((scope, item_id))
    if content is None:
        return None, f"未找到 {scope}/{item_id} 的正文"
    return content, None


def read(path):
    content, error = _read(path)
    return error if error else content


def route(scope, query):
    return _match(query, scope)


def _parse_cli(args):
    if not args:
        return None, "用法: route_reference.py <scope> --query \"...\"\n      route_reference.py --read <scope>/<id>"
    if args[0] in ("--read", "-r", "read"):
        if len(args) != 2:
            return None, "用法: route_reference.py --read <scope>/<id>"
        return _read(args[1])
    scope = args[0]
    if scope not in SCOPES:
        return None, f"未知 scope: {scope}"
    if "--query" not in args:
        return None, "缺少 --query 参数"
    position = args.index("--query")
    if position + 1 >= len(args):
        return None, "--query 缺少查询内容"
    return json.dumps(_match(args[position + 1], scope), ensure_ascii=False, indent=2), None


def cli(args):
    """兼容 Python 调用接口：始终返回可打印字符串。"""
    output, error = _parse_cli(args)
    return error if error else output


if __name__ == "__main__":
    output, error = _parse_cli(sys.argv[1:])
    if error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
    print(output)
