# 细胞培养基配制与补料剂量核算软件 V1.0

面向 CHO 悬浮细胞培养与 Applikon my-Control 3 L 生物反应器场景的 Windows 桌面辅助软件，用于配方计算、培养基配制、补料计划、泵校准、Dose Monitor 数据导入、实际剂量核算、异常审核与批次报告。

> V1.0 是离线计算与数据管理软件，不直接连接、不控制生物反应器、补料泵或其他现场设备，也不下发启停、转速和流量指令。

## 1. 快速启动

### 1.1 本机直接运行

双击 启动软件.bat。启动脚本会依次查找：

1. 软件目录下的 runtime\pythonw.exe（如后续打包）；
2. 当前电脑已有的 pythonw.exe / pyw.exe / python.exe；
3. 本机 Codex 运行环境自带的 Python（仅用于本机交付验证）。

首次启动会在软件目录下创建：

    ApplicationData/
    ├─ database/cell_culture.db
    ├─ imports/
    ├─ reports/
    ├─ backups/
    ├─ logs/
    └─ templates/

### 1.2 使用独立演示数据

双击 启动演示版.bat，将使用 DemoData/ 中的一套完整演示批次，不会影响 ApplicationData/ 中的正式数据。

演示数据包括：CHO 批次 1 个、培养基配方 2 个、泵 4 台、补料计划 28 个事件、泵校准 4 条、Dose Monitor 数据 1540 行、剂量核算结果、异常记录及 Excel/PDF 报告样例。

### 1.3 免安装 EXE 版

已生成免安装窗口程序，可直接分发：

- 目录版：dist/CellCultureDoseSoftware/CellCultureDoseSoftware.exe
- 压缩包：D:\ProgramData\CellCultureDoseSoftware_EXE_V1.0.zip

双击 CellCultureDoseSoftware.exe 或 启动软件.bat 使用正式数据；双击 启动演示版.bat 使用 DemoData 演示批次。EXE 版不需要安装 Python。

### 1.4 其他电脑安装

安装 Python 3.10 或更高版本，并勾选“Add Python to PATH”，然后执行：

    pip install -r requirements.txt
    python main.py

依赖：openpyxl（Excel 报告）、reportlab（PDF 报告）。界面、数据库、CSV 解析和计算使用 Python 标准库（Tkinter / SQLite），无需额外安装 PySide6。

## 2. 功能模块

| 模块 | 功能 |
|---|---|
| 首页与工作台 | 批次、异常、待审核核算、最近导入和报告摘要 |
| 基础数据 | 培养基组分、工艺液、泵、反应器档案；支持启用/停用 |
| 配方管理 | 配方版本、组分明细、发布/停用、新版本复制、计算预览 |
| 配制计算 | 目标体积、浓度、纯度修正、母液体积、定容补足、称量清单 |
| 批次管理 | 批次档案、培养阶段、培养参数、泵—液体绑定 |
| 补料计划 | 计划版本、补料事件、目标量/流速、时间冲突检查、累计量 |
| 泵校准 | 手工录入、my-Control 文件导入、校准点、插值曲线、有效状态 |
| 剂量导入 | 五步向导：文件 → 工作表/表头 → 字段映射 → 预览 → 确认；原文件归档 |
| 剂量核算 | 累计体积差、流速积分、偏差量/偏差率、完成率、数据质量与异常 |
| 异常审核 | 未解决/已解决筛选、处理说明、审计留痕 |
| 报告中心 | 批次 Excel / PDF 报告、报告版本与历史记录 |
| 系统设置 | 操作员、采样间隔、默认单位、数据目录、备份/恢复、操作日志 |

## 3. 核心计算口径

### 3.1 配方与配制

- 质量浓度：质量(g) = 目标浓度(g/L) × 目标体积(L)
- 摩尔浓度：质量(g) = 摩尔浓度(mol/L) × 分子量(g/mol) × 目标体积(L)
- 纯度修正：修正质量(g) = 理论质量(g) ÷ 纯度小数
- 母液体积：母液体积(mL) = 理论质量(g) ÷ 母液浓度(g/L) × 1000
- 定容补足：目标体积(mL) − 各母液体积之和

内部标准单位：质量 g、体积 L（界面显示 mL 时换算）、时间 h、质量浓度 g/L、摩尔浓度 mol/L、流速 mL/h。

### 3.2 泵校准

在相邻实测点之间线性插值：

    Q(x) = Q1 + (x - x1) / (x2 - x1) × (Q2 - Q1)

- 校准点少于 2 个、设置值重复或单位不一致时拒绝插值；
- 超出实测点覆盖范围时不外推，返回警告；
- 同一泵设置新的“有效”校准后，其他有效记录自动标记为“过期”。

### 3.3 实际剂量

- 累计体积差：V实际 = V结束 - V开始，仅在同一连续计数区段内计算；
- 流速积分：V积分 = Σ (Qi + Qi+1) / 2 × Δti，流速统一为 mL/h、时间统一为 h；
- 偏差量：ΔV = V实际 - V计划；
- 偏差率：ΔV ÷ V计划 × 100%；
- 完成率：V实际 ÷ V计划 × 100%；
- 计划量为 0 或缺失时，偏差率/完成率显示“不适用”，不产生除零结果。

### 3.4 数据质量状态

| 状态 | 含义 |
|---|---|
| 有效 | 数据完整、无计数重置/断点/重复时间等疑问 |
| 估算 | 仅有流速积分等替代数据源 |
| 待审核 | 存在计数器重置、采样断点、重复时间或方法差异 |
| 无效 | 数据不足或存在无法解决的关键错误 |

## 4. 文件导入

### 4.1 支持格式

CSV、TXT、TSV、XLSX/XLSM。Excel 可选择工作表和表头行；CSV 自动探测 UTF-8/GB18030/UTF-16 编码与分隔符。

### 4.2 标准字段

时间戳、泵编号、流速、流速单位、累计体积、体积单位、泵状态。

- 时间戳支持 YYYY-MM-DD HH:MM:SS、ISO 8601 和 Excel 日期序列；
- 流速与累计体积可带单位（如 10 mL/h、1.2 L）；
- 导入时统一标准化为流速 mL/h、累计体积 mL；
- 时间戳无法解析、泵编号缺失、关键单位未知属于阻断错误，不允许确认导入；
- 累计体积下降、采样间隔过长、流速为负属于警告，允许导入但生成待审核异常；
- 原始文件复制归档到 imports/<批次>/dose_monitor/ 或 my_control/，并记录 SHA-256。

### 4.3 重复导入

同一批次导入相同哈希的文件时，默认阻止；确需重复导入时需勾选“允许重复导入相同文件”，并填写备注。

## 5. 数据与备份

- SQLite 数据库：ApplicationData/database/cell_culture.db
- 原始导入文件：ApplicationData/imports/
- 报告：ApplicationData/reports/<批次>/
- 备份：ApplicationData/backups/backup_YYYYMMDD_HHMMSS.zip
- 备份内容：数据库快照、导入文件、报告、配置文件清单与 manifest；
- 恢复前自动创建“恢复前备份”，校验数据库 PRAGMA integrity_check 和必要数据表后才替换；
- 配置保存在软件目录 config.json，可在“系统设置”中更改数据目录（需重启）。

## 6. 测试

    python -m unittest -v tests.test_services
    python tests\test_backup.py
    python tests\smoke_ui.py
    python tests\smoke_dialogs.py
    python tests\smoke_wizard_flow.py

- tests/test_services.py：单位换算、配方/纯度/母液、校准插值、剂量核算、导入单位标准化；
- tests/test_backup.py：备份、校验、恢复；
- tests/smoke_ui.py：主窗口与 12 个功能页面创建；
- tests/smoke_dialogs.py：页面、通用表单、剂量导入向导、校准导入对话框；
- tests/smoke_wizard_flow.py：Dose Monitor 与校准文件从读取到提交的完整流程。

## 7. 目录结构

    CellCultureDoseSoftware_V1.0/
    ├─ main.py                     启动入口
    ├─ 启动软件.bat                正式数据启动
    ├─ 启动演示版.bat              演示数据启动
    ├─ config.json                 数据目录与操作员配置
    ├─ requirements.txt
    ├─ app/
    │  ├─ config.py                配置与路径
    │  ├─ db.py                    SQLite 建表、事务、初始化
    │  ├─ repositories.py          数据仓储
    │  ├─ context.py               应用上下文装配
    │  ├─ services/                单位、配方、校准、计划、核算、报告、备份
    │  ├─ importers/               CSV/XLSX 读取、字段映射、Dose/Monitor 适配器
    │  └─ ui/                      主题、组件、主窗口与 12 个页面
    ├─ ApplicationData/            默认正式数据目录（首次运行生成）
    ├─ DemoData/                   演示数据
    ├─ tools/seed_demo.py          演示数据生成脚本
    ├─ tests/                      单元与冒烟测试
    └─ docs/                       设计说明书、用户手册、验收记录

## 8. 设计边界与使用提示

1. my-Control 导出字段的真实含义需以设备样例确认：设置值、理论流量、实测流量或校准后流量；Dose Monitor 累计体积是批次累计、单次累计还是可能自动归零。
2. Dose Monitor 流速是否已应用设备校准参数，需要在导入前确认。
3. 时间戳是否含时区、设备电脑与实验室记录时间是否一致，需要在数据治理中确认。
4. 补料计划跨越计划边界、手动补料、计数器重置和数据断点需要人工确认并记录。
5. 泵校准只适用于对应泵头、泵管、管径、转速和管路配置；更换耗材或配置后应重新校准。
6. 本软件不构成法规符合性声明；用于受监管生产或质量决策前，需另行开展法规适用性评估和计算机化系统验证。
7. 报告中的“估算”“待审核”“无效”结果会在界面和报告中明确标注，不得作为唯一质量决策依据。

## 9. 版本

- 软件版本：V1.0.0
- 数据库结构：V1.0
- 文档依据：《细胞培养基配制与补料剂量核算软件 V1.0 软件概要设计说明书》
- 交付日期：2026-11-11
