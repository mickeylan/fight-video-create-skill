#!/usr/bin/env python3
"""
导出加密资料包中的数据为明文文件
"""
import json
import marshal
import pathlib
import sys
import hashlib as _rh
import hmac as _rm
import lzma as _rl
import io

_R_MAGIC = b"FVB1"
_R_SN = 16384
_R_SR = 8
_R_SP = 1
_R_MEM = 64 * 1024 * 1024
_R_HEAD = 52

def _r_dk(_pw, _salt):
    return _rh.scrypt(_pw, salt=_salt, n=_R_SN, r=_R_SR, p=_R_SP, dklen=32, maxmem=_R_MEM)

def _r_ks(_key, _n, _nonce):
    _out = bytearray()
    _ctr = 0
    while len(_out) < _n:
        _out += _rm.new(_key, _nonce + _ctr.to_bytes(8, "big"), _rh.sha256).digest()
        _ctr += 1
    return bytes(_out[:_n])

def _r_xor(_a, _b):
    _n = min(len(_a), len(_b))
    if _n == 0:
        return b""
    _x = int.from_bytes(_a[:_n], "big") ^ int.from_bytes(_b[:_n], "big")
    return _x.to_bytes(_n, "big")

def _r_open(_pw, _raw):
    if _raw[:4] != _R_MAGIC:
        raise ValueError("bad container")
    _salt = _raw[4:20]
    _nonce = _raw[20:36]
    _tag = _raw[36:52]
    _ct = _raw[52:]
    _key = _r_dk(_pw, _salt)
    _want = _rm.new(_key, _raw[:36] + _ct, _rh.sha256).digest()[:16]
    if not _rm.compare_digest(_want, _tag):
        raise ValueError("bad key or corrupted payload")
    return _rl.decompress(_r_xor(_ct, _r_ks(_key, len(_ct), _nonce)))

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PAYLOAD = _ROOT / "data/core.fvx"

print(f"读取: {_PAYLOAD}")
_BLOB = _r_open(bytes.fromhex("4231bdadaaa68d093e160c3659454674"), _PAYLOAD.read_bytes())
_KIND = _BLOB[:1]
_NS = {"__name__": "_fvcore", "__file__": str(_ROOT / "scripts/_fvcore.py")}

if _KIND == b"S":
    exec(compile(_BLOB[1:].decode("utf-8"), "<fvcore>", "exec"), _NS)
elif _KIND == b"M":
    exec(marshal.loads(_BLOB[1:]), _NS)

_FV = _NS["__fv__"]

def _read_content(path: str) -> str:
    """读取正文内容，通过 stdout 捕获"""
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()
    try:
        try:
            _FV["read"](path)
        except SystemExit as e:
            pass
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()

# 定义所有 scope
SCOPES = ["scenes", "design", "moves", "skills", "scripts"]

# 导出到明文目录
output_dir = _ROOT / "data" / "plain"
output_dir.mkdir(parents=True, exist_ok=True)

total_count = 0

for scope in SCOPES:
    print(f"\n处理 {scope}...")
    
    # 获取该 scope 的所有条目
    result = _FV["route"](scope, "")
    available = result.get("available", [])
    
    if not available:
        result = _FV["route"](scope, "测试")
        available = result.get("available", [])
    
    scope_dir = output_dir / scope
    scope_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存索引
    index_file = scope_dir / "_index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump({"available": available, "routing_rules": result.get("routing_rules", [])}, f, ensure_ascii=False, indent=2)
    
    count = 0
    for item in available:
        item_id = item.get("id", "")
        if not item_id:
            continue
        
        # 读取正文
        try:
            content = _read_content(f"{scope}/{item_id}")
            
            if not content.strip():
                print(f"  跳过 {scope}/{item_id}: 空内容")
                continue
            
            # 保存正文
            if "#" in content[:200] or "##" in content[:200] or "**" in content[:200]:
                out_file = scope_dir / f"{item_id}.md"
            else:
                out_file = scope_dir / f"{item_id}.txt"
            
            out_file.write_text(content, encoding="utf-8")
            
            # 保存带元数据的 JSON
            meta_file = scope_dir / f"{item_id}.meta.json"
            meta = {
                "id": item_id,
                "file": item.get("file", f"{item_id}.txt"),
                "name": item.get("name", item_id),
                "showcase": item.get("showcase", ""),
                "retrieval_hint": item.get("retrieval_hint", ""),
            }
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            count += 1
            total_count += 1
            print(f"  导出 {scope}/{item_id}")
        except Exception as e:
            print(f"  跳过 {scope}/{item_id}: {e}")
    
    print(f"  {scope}: {count} 条")

print(f"\n导出完成！总计 {total_count} 个文件")
print(f"保存位置: {output_dir}")
