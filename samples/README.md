# GovBudgetChecker 样例数据

本目录仅保留回归测试所需的最小样例集：

> **注意**：出于体积考虑，表格中的 PDF 不再随仓库分发，需按下文步骤从对象存储下载到相应路径。

| 类型 | ID | 文件 |
| --- | --- | --- |
| 模板 | `template-national-2024` | `samples/templates/附件2：部门决算模板.pdf` |
| 正确 | `shanghai-2024-good` | `samples/good/上海市普陀区财政局2024年度部门决算.pdf` |
| 错误 | `shanghai-2024-missing-tables` | `samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf` |

其他历史样例（例如 `shanghai-2023-bad-gouji`、`fund-text-mismatch-bad` 等）已移出仓库，避免大文件拖慢同步速度。需要时可从对象存储拉取：

1. 通过内部 Wiki 获取最新的样例镜像地址，并设置环境变量：

   ```bash
   export SAMPLES_MIRROR="https://<internal-oss>/govbudgetchecker/samples/2024-09-25"
   ```

2. 使用 `curl` 批量拉取所需文件（以下命令可按需增删条目）：

   ```bash
   python - <<'PY'
   import os
   import pathlib
   import urllib.request

   BASE = os.environ.get("SAMPLES_MIRROR")
   if not BASE:
       raise SystemExit("请先设置 SAMPLES_MIRROR 环境变量，参见 README 指引。")

   targets = {
       "template-national-2024": "samples/templates/附件2：部门决算模板.pdf",
       "shanghai-2024-good": "samples/good/上海市普陀区财政局2024年度部门决算.pdf",
       "shanghai-2024-missing-tables": "samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf",
       "shanghai-2023-bad-gouji": "samples/bad/上海市XX局_2023决算公开_支出勾稽错误.pdf",
       "fund-text-mismatch-bad": "samples/bad/政府性基金_口径不一致_示例.pdf",
       "shanghai-2024-lands": "samples/bad/上海市普陀区规划和自然资源局 2024 年度部门决算.pdf",
   }

   for name, relative in targets.items():
       url = f"{BASE.rstrip('/')}/{relative}"
       dest = pathlib.Path(relative)
       dest.parent.mkdir(parents=True, exist_ok=True)
       print(f"Downloading {name} from {url} …")
       urllib.request.urlretrieve(url, dest)
   PY
   ```

如需扩充样例，请先更新 `samples/manifest.yaml`，并执行 `pytest tests/test_samples.py` 确保元数据完整。
