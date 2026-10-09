#!/usr/bin/env python3
"""fight-video 资料库检索入口（明文版本）。

用法：
    python -X utf8 route_reference.py <scenes|design|moves|skills|scripts> --query "..."
    python -X utf8 route_reference.py --read <scope>/<id>

所有资料存储在 data/plain/ 目录下，直接可读。
"""
import json
import sys
import pathlib
from pathlib import Path as _rP

_ROOT = _rP(__file__).resolve().parents[1]
_PLAIN_DIR = _ROOT / "data" / "plain"

# 加载索引数据
_index = {}

for scope in ["scenes", "design", "moves", "skills", "scripts"]:
    scope_dir = _PLAIN_DIR / scope
    _index[scope] = {}
    if scope_dir.exists():
        for f in scope_dir.glob("*.meta.json"):
            item_id = f.stem.replace(".meta", "")
            with open(f, "r", encoding="utf-8") as fp:
                _index[scope][item_id] = json.load(fp)

def _load_content(scope: str, item_id: str) -> str:
    """读取正文内容"""
    scope_dir = _PLAIN_DIR / scope
    # 尝试各种扩展名
    for ext in [".txt", ".md", ".json"]:
        f = scope_dir / f"{item_id}{ext}"
        if f.exists():
            return f.read_text(encoding="utf-8")
    return f"未找到 {scope}/{item_id}"

def _get_available(scope: str):
    """获取该 scope 的所有可用条目"""
    if scope not in _index:
        return []
    result = []
    for item_id, data in _index[scope].items():
        if isinstance(data, dict) and not item_id.startswith("_"):
            result.append({
                "id": item_id,
                "file": data.get("file", f"{item_id}.txt"),
                "name": data.get("name", item_id),
                "showcase": data.get("showcase", ""),
                "retrieval_hint": data.get("retrieval_hint", ""),
            })
    return result

def _match(query: str, scope: str) -> dict:
    """关键词匹配"""
    query_lower = query.lower()
    query_words = [w for w in query_lower.replace(" ", "").split() if w]
    
    result = {
        "scope": scope,
        "query": query,
        "match_rule": "关键词匹配",
        "primary": None,
        "eligible": [],
        "weak_fallback": False,
        "available": _get_available(scope),
        "routing_rules": [],
        "conflict_resolution": []
    }
    
    if scope not in _index:
        return result
    
    candidates = []
    for item_id, data in _index[scope].items():
        if item_id.startswith("_"):
            continue
        if not isinstance(data, dict):
            continue
        
        # 读取正文进行匹配
        content = _load_content(scope, item_id)
        
        # 简单关键词匹配
        text = (content + json.dumps(data, ensure_ascii=False)).lower()
        hits = sum(1 for w in query_words if w in text)
        
        if hits > 0 or not query_words:
            candidates.append({
                "id": item_id,
                "file": data.get("file", f"{item_id}.txt"),
                "name": data.get("name", item_id),
                "hit_count": hits,
                "weighted_score": hits * 2,
                "field_hits": {"route_keywords": query_words},
                "matched_keywords": [w for w in query_words if w in text],
                "showcase": data.get("showcase", ""),
                "retrieval_hint": data.get("retrieval_hint", ""),
            })
    
    # 按命中数排序
    candidates.sort(key=lambda x: (-x["hit_count"], -x["weighted_score"]))
    
    if candidates:
        result["primary"] = candidates[0]
        result["eligible"] = candidates[:5]
    
    return result

def _read(path: str) -> str:
    """读取指定路径的正文"""
    parts = path.split("/")
    if len(parts) >= 2:
        scope, item_id = parts[0], parts[1]
    else:
        return f"无效路径: {path}"
    
    return _load_content(scope, item_id)

def cli(args):
    """CLI 接口"""
    if not args:
        print("用法: route_reference.py <scenes|design|moves|skills|scripts> --query \"...\"")
        print("      route_reference.py --read <scope>/<id>")
        return
    
    if args[0] in ("--read", "-r", "read"):
        if len(args) < 2:
            return "用法: route_reference.py --read <scope>/<id>"
        return _read(args[1])
    
    if args[0] in ("scenes", "design", "moves", "skills", "scripts"):
        query = ""
        for i, arg in enumerate(args):
            if arg == "--query" and i + 1 < len(args):
                query = args[i + 1]
                break
        return json.dumps(_match(query, args[0]), ensure_ascii=False, indent=2)
    
    return f"未知命令: {args[0]}"

def read(path: str) -> str:
    """读取接口"""
    return _read(path)

def route(scope: str, query: str) -> dict:
    """路由接口"""
    return _match(query, scope)

if __name__ == "__main__":
    _argv = sys.argv[1:]
    if _argv and _argv[0] in ("--read", "-r", "read"):
        if len(_argv) < 2:
            print("用法: route_reference.py --read <scope>/<id>", file=sys.stderr)
            sys.exit(1)
        raise SystemExit(_read(_argv[1]))
    
    if not _argv:
        print("用法: route_reference.py <scenes|design|moves|skills|scripts> --query \"...\"", file=sys.stderr)
        sys.exit(1)
    
    scope = _argv[0]
    query = ""
    for i, arg in enumerate(_argv):
        if arg == "--query" and i + 1 < len(_argv):
            query = _argv[i + 1]
            break
    
    if scope not in ["scenes", "design", "moves", "skills", "scripts"]:
        print(f"未知 scope: {scope}", file=sys.stderr)
        sys.exit(1)
    
    raise SystemExit(json.dumps(_match(query, scope), ensure_ascii=False, indent=2))
