"""Convert the game registry workbook into a machine-readable JSON config.

Usage:
    python scripts/game_registry_to_json.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "knowledge" / "game_registry.xlsx"
DEFAULT_OUTPUT = REPO_ROOT / "config" / "game_registry.json"

SHEET_ALIASES = {
    "games": ["游戏基础信息", "game_registry", "games"],
    "sources": ["官方信息源", "sources", "source"],
    "event_rules": ["运营事件规则", "event_rules", "events"],
    "page_mappings": ["官方页面映射", "page_mappings", "pages"],
}


def _normalize(name: str) -> str:
    return re.sub(r"[\s_\-\.]+", "", name.strip().lower())


def _resolve_sheets(sheet_names: list[str]) -> dict[str, str]:
    normalized = {name: _normalize(name) for name in sheet_names}

    def find_exact(key: str) -> str | None:
        for alias in SHEET_ALIASES[key]:
            target = _normalize(alias)
            for name, norm in normalized.items():
                if norm == target:
                    return name
        return None

    def find_contains(key: str) -> str | None:
        for alias in SHEET_ALIASES[key]:
            target = _normalize(alias)
            if not target:
                continue
            for name, norm in normalized.items():
                if target in norm:
                    return name
        return None

    resolved = {}
    for key in SHEET_ALIASES:
        name = find_exact(key)
        if name is None:
            name = find_contains(key)
        if name is None:
            available = ", ".join(sheet_names) or "无"
            raise ValueError(f"找不到 {key} 对应的 Sheet（现有 Sheet: {available}）")
        resolved[key] = name
    return resolved


def _clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, pd.Timedelta):
        return None if pd.isna(value) else value.total_seconds()
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _sheet_to_records(path: Path, sheet_name: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=object, engine="openpyxl")
    df = df.dropna(axis=0, how="all")

    unnamed = df.columns.astype(str).str.match(r"^Unnamed: \d+$")
    all_empty = df.isna().all(axis=0)
    df = df.loc[:, ~(unnamed & all_empty)]
    df = df.dropna(axis=1, how="all")
    df.columns = [str(col).strip() for col in df.columns]

    records = []
    for _, row in df.iterrows():
        record = {str(col): _clean_value(value) for col, value in row.items()}
        if any(value is not None for value in record.values()):
            records.append(record)
    return records


def _resolve_input(arg: str | None) -> Path:
    if arg:
        path = Path(arg)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"输入文件不存在: {path}")
        return path

    if DEFAULT_INPUT.is_file():
        return DEFAULT_INPUT

    candidates = sorted(REPO_ROOT.joinpath("knowledge").glob("*.xlsx"))
    if len(candidates) == 1:
        print(f"提示: 未找到 {DEFAULT_INPUT.name}，使用 {candidates[0].name}")
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"未找到输入文件: {DEFAULT_INPUT} 或 knowledge/ 下任何 xlsx")
    raise FileNotFoundError(
        "knowledge/ 下存在多个 xlsx，请用 --input 指定: "
        + ", ".join(path.name for path in candidates)
    )


def _validate_relations(data: dict[str, list[dict]]) -> None:
    game_ids = {
        record["game_id"] for record in data["games"] if record.get("game_id") is not None
    }
    for key in ("sources", "event_rules", "page_mappings"):
        orphan_ids = sorted(
            {
                record["game_id"]
                for record in data[key]
                if record.get("game_id") is not None and record["game_id"] not in game_ids
            },
            key=str,
        )
        missing_relation = sum(1 for record in data[key] if record.get("game_id") is None)
        if orphan_ids:
            shown = orphan_ids[:5]
            suffix = "..." if len(orphan_ids) > 5 else ""
            print(f"  警告: {key} 有 {len(orphan_ids)} 个 game_id 不在 games 中: {shown}{suffix}")
        if missing_relation:
            print(f"  提示: {key} 有 {missing_relation} 条记录缺少 game_id")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="将游戏运营知识库 Excel 转换为 JSON 配置")
    parser.add_argument("--input", help=f"输入 xlsx 路径（默认 {DEFAULT_INPUT}）")
    parser.add_argument("--output", help=f"输出 json 路径（默认 {DEFAULT_OUTPUT}）")
    args = parser.parse_args(argv)

    input_path = _resolve_input(args.input)
    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path

    print(f"输入: {input_path}")
    with pd.ExcelFile(input_path, engine="openpyxl") as excel:
        sheet_names = excel.sheet_names
        resolved = _resolve_sheets(sheet_names)

        data = {}
        for key, sheet_name in resolved.items():
            data[key] = _sheet_to_records(input_path, sheet_name)
            print(f"  {key} <- {sheet_name}")

        skipped = [name for name in sheet_names if name not in set(resolved.values())]
        if skipped:
            print(f"跳过未映射 Sheet: {', '.join(skipped)}")

    _validate_relations(data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"输出: {output_path}")
    print(f"games: {len(data['games'])}")
    print(f"sources: {len(data['sources'])}")
    print(f"event_rules: {len(data['event_rules'])}")
    print(f"page_mappings: {len(data['page_mappings'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
