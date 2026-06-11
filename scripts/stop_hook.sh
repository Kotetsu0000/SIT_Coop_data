#!/bin/bash
# Claude Code の Stop フック(claude_auto_fix.yml で使用)。
# test.py が通らない状態で Claude が作業を終了しようとしたらブロックし、
# 修正を続けさせる。暴走は claude_args の --max-turns で抑止される。
set -u

if output=$(uv run python test.py 2>&1); then
    exit 0
fi

{
    echo "test.py が失敗しています。終了する前に修正を完了してください。"
    echo "overrides.json / known_gaps.json を修正し、"
    echo "「uv run python fetch_coop_data.py --local」で再生成してから再確認すること。"
    echo ""
    echo "--- test.py の出力 ---"
    echo "$output"
} >&2
exit 2
