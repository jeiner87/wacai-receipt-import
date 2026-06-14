---
name: wacai-receipt-import
description: "This skill should be used when the user wants to import receipt or transaction images into the Wacai accounting platform. It handles the full workflow: parse images with AI vision to get JSON, then directly call the import function in Python with the JSON — no intermediate files. Trigger phrases: 导入挖财, 上传账单到挖财, 解析收支图片, 记账导入, wacai receipt import."
agent_created: true
---

# 挖财收支图片导入技能

将收支截图（1-5 张）通过 AI 解析后，自动导入挖财记账平台。
**核心原则：不生成任何中间文件（无 JSON 文件、无 CSV 文件），直接在内存中传 JSON 对象到导入函数。**

## 完整工作流

### 第一步：收集图片

- 接受用户上传的 1-5 张收支记录截图（建议每张不超过两屏高度）
- 图片来源：微信账单、支付宝账单、银行流水截图等

### 第二步：解析图片为 JSON（内存中，不写文件）

使用以下提示词调用视觉模型解析每张图片（可批量处理多张）：

```
解析图片中的收支记录为规范JSON，仅以JSON返回，不要添加多余的描述。收付账户统一为：<收付账户>，类型规则：还款->收入，转账->支出。

格式要求参见 references/wacai_json_schema.md
```

注意事项：
- 将 `<收付账户>` 替换为用户实际使用的账户名（如不确定，先询问用户）
- 多张图片的 JSON 结果需合并为一个数组，并按日期时间排序（升序）
- 去除明显重复的条目（同日期、同金额、同类别的记录）
- 若图片内容模糊或无法识别，告知用户并跳过

详细字段规范和示例见：`references/wacai_json_schema.md`

### 第三步：直接在 Python 中调用导入函数（关键！）

**不要写任何文件**。拿到 JSON 对象（Python list[dict]）后，直接在 Python 代码中调用：

```python
import sys, json, os

# 将 import_receipt.py 所在目录加入 sys.path
import sys, os
skill_dir = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", "wacai-receipt-import", "scripts")
if skill_dir not in sys.path:
    sys.path.insert(0, skill_dir)

from import_receipt import import_records

token = "<X-Access-Token>"
book_name = "<日常账本名称>"
records = [
    {
        "日期时间": "2026-06-14 14:16:27",
        "类型": "支出",
        "类别": "餐饮/外卖",
        "金额": 16.52,
        "币种": "人民币",
        "收付款人": "",
        "收付账户": "交通信用卡 2690",
        "参与人": "自己",
        "标签": "",
        "商家": "上海拉扎斯信息(饿了么)",
        "属性": "",
        "备注": ""
    }
    # ... 更多记录
]

import_records(token, book_name, records)
```

`import_records()` 函数内部会自动：
1. 将 JSON 对象转为 CSV（内存临时文件，自动清理）
2. 上传到挖财
3. 查询账本 ID
4. 提交导入任务
5. 轮询进度直到完成

**此方式完全避免了 shell 转义问题和中间文件。**

### 第四步：获取 X-Access-Token（若用户未提供）

引导用户获取 Token：
1. 访问 https://jz.wacaijizhang.com/jz-pc/flow 并登录
2. 按 F12 打开开发者工具 → Network 标签 → 过滤 Fetch/XHR
3. 点击任意请求 → Headers → 找到 `X-Access-Token` 字段并复制

### 第五步：反馈结果

- 展示导入摘要（记录数、日期范围、金额统计）
- 提示用户在挖财 App 或网页端核实导入结果
- 若导入失败，显示错误信息并提供排查建议

## 禁止的操作

- ❌ 不要将 JSON 写入 `.json` 文件
- ❌ 不要生成 `.csv` 文件到工作目录
- ❌ 不要使用 `python import_receipt.py --json-file` 或 CLI 方式传参
- ✅ 直接在 Python 中调用 `import_records()` 函数

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| Token 失效（401）| 重新登录挖财网页版，刷新 Token |
| 账本不存在 | 检查账本名称是否完全匹配（含空格） |
| 部分记录未导入 | 检查日期格式是否符合 `YYYY-MM-DD HH:MM:SS` |
| 图片解析错误 | 尝试裁剪图片、提高清晰度，或手动核对 |

## 参考文件

- `references/wacai_json_schema.md` — 完整字段规范、类型映射规则和 JSON 示例
- `scripts/import_receipt.py` — 挖财 API 导入脚本（提供 `import_records()` 函数）
