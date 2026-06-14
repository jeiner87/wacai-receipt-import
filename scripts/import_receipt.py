#!/usr/bin/env python3
"""
import_receipt.py - 将收支记录导入挖财记账本

用法：
  # 方式一：直接传 JSON 字符串（推荐，AI 调用）
  python import_receipt.py <TOKEN> <账本名称> --json '[{"日期时间":"..."}]'

  # 方式二：传 JSON 文件路径
  python import_receipt.py <TOKEN> <账本名称> --json-file records.json

  # 方式三：直接传 CSV 文件路径（向后兼容）
  python import_receipt.py <TOKEN> <账本名称> <CSV文件路径>

X-Access-Token 获取方式：
  1. 访问 https://jz.wacaijizhang.com/jz-pc/flow 并登录
  2. F12 → Network → Fetch/XHR → 任意请求 Headers 中找到 X-Access-Token
"""

import requests
import time
import sys
import os
import csv
import json
import tempfile
import argparse
from datetime import datetime

# ── 挖财 API 端点 ──────────────────────────────────────────────────────────────

BASE_URL = "https://jz.wacaijizhang.com"

ENDPOINT_UPLOAD   = f"{BASE_URL}/jz-pc/api/file/excelUpload"
ENDPOINT_QUERY_BOOKS = f"{BASE_URL}/jz-pc/api/v2/book/web/query"
ENDPOINT_IMPORT   = f"{BASE_URL}/jz-pc/api/data/excel/import"
ENDPOINT_PROGRESS = f"{BASE_URL}/jz-pc/api/data/excel/import/progress"

# ── CSV 列定义 ──────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "日期时间", "类型", "类别", "金额", "币种",
    "收付款人", "收付账户", "参与人", "标签", "商家", "属性", "备注",
]

# ── 公共请求头 ──────────────────────────────────────────────────────────────────

def _headers(token: str, content_type: str = None) -> dict:
    h = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Origin": BASE_URL,
        "Pragma": "no-cache",
        "Referer": f"{BASE_URL}/jz-pc/import",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        ),
        "X-Access-Token": token,
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


# ── 核心步骤 ──────────────────────────────────────────────────────────────────

def json_to_csv(records: list, output_path: str | None = None) -> str:
    """
    将收支记录 JSON 列表转换为 CSV 文件。
    返回生成的 CSV 文件路径。
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            suffix=".csv",
            prefix=f"wacai_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}_",
        )
        os.close(fd)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            row = {k: record.get(k, "") for k in CSV_FIELDS}
            writer.writerow(row)

    return output_path


def upload_file(token: str, file_path: str) -> str:
    """上传文件到挖财，返回 sourceId。"""
    basename = os.path.basename(file_path)
    if file_path.endswith(".csv"):
        mime_type = "text/csv"
    elif file_path.endswith((".xls", ".xlsx")):
        mime_type = "application/vnd.ms-excel"
    else:
        mime_type = "application/octet-stream"

    with open(file_path, "rb") as f:
        files = {"file": (basename, f, mime_type)}
        resp = requests.post(ENDPOINT_UPLOAD, headers=_headers(token), files=files)

    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0 or not result.get("data"):
        raise RuntimeError(f"文件上传失败：{result}")

    source_id = result["data"]["sourceId"]
    print(f"  [OK] 文件上传成功，sourceId = {source_id}")
    return source_id


def query_book_id(token: str, book_name: str) -> str:
    """查询账本 ID。"""
    resp = requests.get(
        ENDPOINT_QUERY_BOOKS,
        headers=_headers(token, "application/x-www-form-urlencoded"),
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0 or not result.get("data"):
        raise RuntimeError(f"查询账本失败：{result}")

    books = result["data"].get("books", [])
    for book in books:
        if book["name"] == book_name:
            book_id = str(book["id"])
            print(f"  [OK] 找到账本「{book_name}」，ID = {book_id}")
            return book_id

    available = [b["name"] for b in books]
    raise RuntimeError(f"未找到账本「{book_name}」。可用账本：{available}")


def start_import(token: str, source_id: str, book_id: str) -> bool:
    """提交导入任务，返回是否成功。"""
    payload = {"sourceId": source_id, "bookId": book_id, "aiMatchCategory": False}
    resp = requests.post(
        ENDPOINT_IMPORT,
        headers=_headers(token, "application/json"),
        json=payload,
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        raise RuntimeError(f"提交导入失败：{result}")

    success = result["data"].get("success", False)
    print(f"  [OK] 导入任务已提交（success={success}）")
    return success


def check_progress(token: str, source_id: str) -> int:
    """查询导入进度，返回状态值（1=完成）。"""
    resp = requests.get(
        f"{ENDPOINT_PROGRESS}?sourceId={source_id}",
        headers=_headers(token, "application/x-www-form-urlencoded"),
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        raise RuntimeError(f"查询进度失败：{result}")

    return result["data"].get("status", 0)


def wait_for_complete(token: str, source_id: str, interval: int = 2, timeout: int = 300):
    """轮询导入进度，直到完成或超时。"""
    deadline = time.time() + timeout
    while True:
        status = check_progress(token, source_id)
        print(f"  导入状态：{status}（1=完成）")
        if status == 1:
            print("  [OK] 导入完成！")
            return
        if time.time() > deadline:
            raise TimeoutError("导入超时，请到挖财网页端手动查看结果")
        time.sleep(interval)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(token: str, book_name: str, records: list):
    """
    完整导入流程：
    1. JSON → CSV
    2. 上传文件
    3. 查询账本 ID
    4. 提交导入
    5. 等待完成
    """
    print(f"==== 挖财导入开始 ====")
    print(f"  账本：{book_name}")
    print(f"  记录数：{len(records)}")

    # Step 1: JSON → CSV
    print(f"\n[1/5] 生成 CSV 文件...")
    csv_path = json_to_csv(records)
    print(f"  [OK] 已生成：{csv_path}")

    # Step 2: 上传文件
    print(f"\n[2/5] 上传文件...")
    source_id = upload_file(token, csv_path)

    # Step 3: 查询账本
    print(f"\n[3/5] 查询账本 ID...")
    book_id = query_book_id(token, book_name)

    # Step 4: 提交导入
    print(f"\n[4/5] 提交导入任务...")
    start_import(token, source_id, book_id)

    # Step 5: 等待完成
    print(f"\n[5/5] 等待导入完成...")
    wait_for_complete(token, source_id)

    print(f"\n==== 全部完成 ====")
    print(f"  请在挖财 App 或网页端核实导入结果。")


# ── CLI 入口 ───────────────────────────────────────────────────────────────────

def _load_records_from_arg(token, book_name, json_str, json_file, csv_file):
    """根据参数来源加载记录列表。"""
    if json_str:
        records = json.loads(json_str)
        if not isinstance(records, list):
            records = [records]
        return records

    if json_file:
        with open(json_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            records = [records]
        return records

    if csv_file:
        # 向后兼容：直接上传 CSV，跳过 JSON 解析步骤
        print(f"==== 直接上传 CSV 模式（向后兼容）====")
        print(f"  账本：{book_name}")
        print(f"  文件：{csv_file}")

        print(f"\n[1/4] 上传文件...")
        source_id = upload_file(token, csv_file)

        print(f"\n[2/4] 查询账本 ID...")
        book_id = query_book_id(token, book_name)

        print(f"\n[3/4] 提交导入任务...")
        start_import(token, source_id, book_id)

        print(f"\n[4/4] 等待导入完成...")
        wait_for_complete(token, source_id)

        print(f"\n==== 全部完成 ====")
        return None  # 已完成，无需再 run()

    raise ValueError("必须提供 --json / --json-file / <CSV文件路径> 之一")


def main():
    parser = argparse.ArgumentParser(
        description="将收支记录导入挖财记账本",
        epilog="获取 X-Access-Token：登录 https://jz.wacaijizhang.com/jz-pc/flow 后 F12 查看请求 Headers",
    )
    parser.add_argument("token", help="X-Access-Token")
    parser.add_argument("book_name", help="账本名称（如：日常账本）")
    parser.add_argument("--json",       dest="json_str",   help="直接传入 JSON 字符串")
    parser.add_argument("--json-file",  dest="json_file",  help="JSON 文件路径")
    parser.add_argument("csv_file", nargs="?", default=None, help="CSV 文件路径（向后兼容）")

    args = parser.parse_args()

    result = _load_records_from_arg(
        args.token, args.book_name,
        args.json_str, args.json_file, args.csv_file,
    )

    if result is not None:
        run(args.token, args.book_name, result)


# ── 模块可调用的快捷入口 ────────────────────────────────────────────────────

def import_records(token: str, book_name: str, records: list):
    """
    Python 模块直接调用（推荐，避免 shell 转义）：
        from import_receipt import import_records
        import_records(token, book_name, [{"日期时间":"..."}])
    """
    run(token, book_name, records)


if __name__ == "__main__":
    main()
