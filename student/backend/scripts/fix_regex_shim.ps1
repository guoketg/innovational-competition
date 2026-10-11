# ============================================================
# 修复 Windows Smart App Control 拦截 regex 原生扩展
# 背景：SAC 拦截 regex 包未签名的 _regex.pyd（"应用程序控制策略
# 已阻止此文件"），导致 sentence_transformers/transformers 无法导入。
# 本脚本把 regex 包挪开，写入一个映射到标准库 re 的 regex.py 占位。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\fix_regex_shim.ps1
# 如需恢复原 regex：删除 regex.py，并把 regex_orig 改回 regex。
# ============================================================
$ErrorActionPreference = 'Stop'

$site = Join-Path $PSScriptRoot '..\.venv\Lib\site-packages'
$site = [System.IO.Path]::GetFullPath($site)
$regexDir = Join-Path $site 'regex'
$regexOrig = Join-Path $site 'regex_orig'
$regexPy = Join-Path $site 'regex.py'

if (-not (Test-Path $site)) {
    Write-Host "未找到 site-packages: $site" -ForegroundColor Red
    exit 1
}

# 1) 若原 regex 包存在且尚未备份 → 挪开
if ((Test-Path $regexDir) -and -not (Test-Path $regexOrig)) {
    [System.IO.Directory]::Move($regexDir, $regexOrig)
    Write-Host "[OK] regex/ -> regex_orig/" -ForegroundColor Green
} elseif (-not (Test-Path $regexDir)) {
    Write-Host "[SKIP] regex/ 不存在（可能已处理）"
} else {
    Write-Host "[SKIP] regex_orig/ 已存在，保留现状"
}

# 2) 写入 stdlib re shim
if (-not (Test-Path $regexPy)) {
    $shim = @'
"""regex 包的标准库 re 替代实现（Windows Smart App Control 拦截了
regex 未签名的原生扩展 _regex.pyd）。transformers 仅在文档解析等非
BGE 推理路径使用 regex 且均为标准 re 兼容 API；BGE 切词走 Rust 版
tokenizers，不依赖 python regex。"""
import re as _re
from re import *  # noqa: F401,F403
Pattern = _re.Pattern
Match = _re.Match
RegexFlag = _re.RegexFlag
error = _re.error
compile = _re.compile
search = _re.search
match = _re.match
fullmatch = _re.fullmatch
findall = _re.findall
finditer = _re.finditer
sub = _re.sub
subn = _re.subn
split = _re.split
escape = _re.escape
purge = _re.purge
VERSION = "stdlib-re-shim"
'@
    [System.IO.File]::WriteAllText($regexPy, $shim, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] 已写入 regex.py shim" -ForegroundColor Green
} else {
    Write-Host "[SKIP] regex.py 已存在"
}

# 3) 验证
Write-Host "验证导入..."
& (Join-Path $site '..\..\Scripts\python.exe') -c "import sentence_transformers, transformers; print('sentence_transformers 导入成功')"
