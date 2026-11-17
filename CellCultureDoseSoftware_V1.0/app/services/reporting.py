# -*- coding: utf-8 -*-
"""报告服务：汇总批次数据并导出 Excel / PDF。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..db import now_iso
from ..importers.common import safe_name, sha256_file
from ..repositories import Repositories
from .units import fmt


class ReportError(RuntimeError):
    pass


def _v(value: Any) -> Any:
    return "" if value is None else value


class ReportService:
    def __init__(self, repos: Repositories, settings):
        self.repos = repos
        self.settings = settings
        self.db = repos.db

    # ---------- 数据汇总 ----------
    def collect(self, batch_id: str) -> dict:
        batch = self.db.q1(
            "SELECT b.*, r.reactor_code, r.reactor_name FROM batch_info b "
            "LEFT JOIN reactor_info r ON r.reactor_id=b.reactor_id WHERE b.batch_id=?", (batch_id,))
        if not batch:
            raise ReportError("批次不存在")
        batch = dict(batch)
        stages = self.repos.batches.stages(batch_id)
        params = self.repos.batches.parameters(batch_id)
        mappings = self.repos.batches.mappings(batch_id)
        preparations = [dict(r) for r in self.db.q(
            "SELECT p.*, f.formula_code, f.formula_name, f.version_no FROM preparation_record p "
            "JOIN formula_info f ON f.formula_id=p.formula_id WHERE p.batch_id=? ORDER BY p.prepared_at", (batch_id,))]
        plan = self.repos.plans.latest(batch_id)
        events = self.repos.plans.events(plan["plan_id"]) if plan else []
        pump_ids = {m["pump_id"] for m in mappings} | {e["pump_id"] for e in events}
        calibrations = []
        for pump_id in sorted(pump_ids):
            for rec in self.repos.calibrations.records(pump_id):
                rec = dict(rec)
                rec["points"] = self.repos.calibrations.points(rec["calibration_id"])
                calibrations.append(rec)
        imports = self.repos.imports.list_recent(batch_id, 500)
        calculations = self.repos.doses.list_for_batch(batch_id)
        from .manual_feed import ManualFeedService
        manual = ManualFeedService(self.db).list_for_batch(batch_id)
        commercial = [dict(r) for r in self.db.q("SELECT * FROM commercial_medium_record WHERE batch_id=? ORDER BY used_at", (batch_id,))]
        anomalies = self.repos.anomalies.list_for_batch(batch_id)
        reports = self.repos.reports.list_for_batch(batch_id)
        return {"batch": batch, "stages": stages, "parameters": params, "mappings": mappings,
                "preparations": preparations, "plan": plan, "events": events,
                "calibrations": calibrations, "imports": imports, "calculations": calculations, "manual": manual, "commercial": commercial,
                "anomalies": anomalies, "reports": reports}

    def _target_dir(self, batch_code: str) -> Path:
        folder = self.settings.path("reports", safe_name(batch_code))
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _record(self, batch_id: str, report_type: str, path: Path, user: str, notes: str = "") -> None:
        self.repos.reports.create({
            "batch_id": batch_id,
            "report_type": report_type,
            "file_path": str(path),
            "file_hash": sha256_file(path),
            "generated_by": user,
            "notes": notes,
        })
        self.repos.logs.add(user, "生成报告", "report", path.name, after={"path": str(path), "type": report_type})

    # ---------- Excel ----------
    def generate_excel(self, batch_id: str, user: str) -> Path:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
            from openpyxl.utils import get_column_letter
        except ImportError as exc:
            raise ReportError("缺少 openpyxl，无法生成 Excel 报告") from exc

        data = self.collect(batch_id)
        batch = data["batch"]
        wb = Workbook()
        wb.remove(wb.active)

        title_font = Font(name="Microsoft YaHei", size=16, bold=True, color="1F4E79")
        head_font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
        body_font = Font(name="Microsoft YaHei", size=10)
        head_fill = PatternFill("solid", fgColor="1F4E79")
        alt_fill = PatternFill("solid", fgColor="EAF1F8")
        thin = Side(style="thin", color="BFBFBF")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        def write_sheet(name: str, headers: list[str], rows: list[list[Any]], widths: dict[int, float] | None = None,
                        note: str = ""):
            ws = wb.create_sheet(name[:31])
            ws.sheet_view.showGridLines = False
            ws.append(headers)
            for col, _ in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col)
                cell.font = head_font
                cell.fill = head_fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = border
            for r_idx, row in enumerate(rows, 2):
                ws.append([_v(v) for v in row])
                for c_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    cell.font = body_font
                    cell.border = border
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                    if r_idx % 2 == 0:
                        cell.fill = alt_fill
            for idx in range(1, len(headers) + 1):
                width = (widths or {}).get(idx)
                if not width:
                    values = [str(_v(ws.cell(row=r, column=idx).value)) for r in range(1, min(ws.max_row, 200) + 1)]
                    width = max(10, min(42, max((sum(1.8 if ord(ch) > 127 else 1 for ch in v) for v in values), default=10) + 3))
                ws.column_dimensions[get_column_letter(idx)].width = width
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{get_column_letter(max(1, len(headers)))}{max(1, ws.max_row)}"
            if note:
                ws.cell(row=ws.max_row + 2, column=1, value=note).font = Font(
                    name="Microsoft YaHei", size=9, italic=True, color="7F7F7F")
            return ws

        # 封面/概览
        ws = wb.create_sheet("批次概览")
        ws.sheet_view.showGridLines = False
        ws["A1"] = "细胞培养基配制与补料剂量核算报告"
        ws["A1"].font = title_font
        ws.merge_cells("A1:D1")
        ws["A2"] = f"批次编号：{batch['batch_code']}"
        ws["A2"].font = Font(name="Microsoft YaHei", size=12, bold=True)
        meta = [
            ("项目名称", batch.get("project_name")), ("培养体系", batch.get("culture_system")),
            ("反应器", batch.get("reactor_code") or ""), ("工作体积 (mL)", batch.get("working_volume_ml")),
            ("批次状态", batch.get("status")), ("开始时间", batch.get("start_time")),
            ("结束时间", batch.get("end_time")), ("创建人", batch.get("created_by")),
            ("报告生成时间", now_iso()), ("报告生成人", user),
        ]
        for i, (k, v) in enumerate(meta, 4):
            ws.cell(row=i, column=1, value=k).font = Font(name="Microsoft YaHei", size=10, bold=True)
            ws.cell(row=i, column=2, value=_v(v)).font = body_font
        summary = [
            ("培养阶段", len(data["stages"])), ("培养参数记录", len(data["parameters"])),
            ("泵-液体绑定", len(data["mappings"])), ("配制记录", len(data["preparations"])),
            ("补料事件", len(data["events"])), ("设备导入", len(data["imports"])),
            ("剂量核算", len(data["calculations"])), ("异常记录", len(data["anomalies"])),
            ("未解决异常", sum(1 for a in data["anomalies"] if a["status"] == "未解决")),
        ]
        row0 = 4 + len(meta) + 1
        ws.cell(row=row0, column=1, value="数据摘要").font = Font(name="Microsoft YaHei", size=12, bold=True, color="1F4E79")
        for i, (k, v) in enumerate(summary, row0 + 1):
            ws.cell(row=i, column=1, value=k).font = body_font
            ws.cell(row=i, column=2, value=v).font = body_font
        disclaimer = ("说明：本报告由软件依据已保存的数据自动生成。标记为“估算”“待审核”或“无效”的核算结果"
                      "不得作为唯一质量决策依据；原始导入记录与人工修正记录应一并保存。")
        ws.cell(row=row0 + len(summary) + 2, column=1, value=disclaimer).font = Font(
            name="Microsoft YaHei", size=9, italic=True, color="7F7F7F")
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 42

        # 阶段与参数
        write_sheet("培养阶段与参数",
                    ["阶段", "阶段开始", "阶段结束", "参数", "数值", "单位", "记录时间", "备注"],
                    [[s["stage_name"], s.get("start_time"), s.get("end_time"), "", "", "", "", s.get("notes")]
                     for s in data["stages"]] +
                    [["", "", "", p["param_name"], p.get("param_value"), p.get("unit"), p.get("recorded_at"), p.get("notes")]
                     for p in data["parameters"]])

        # 配方与配制
        prep_rows = []
        for p in data["preparations"]:
            prep_rows.append([p.get("formula_code"), p.get("formula_name"), p.get("version_no"),
                              p.get("target_volume"), p.get("volume_unit"),
                              p.get("theoretical_amount"), p.get("corrected_amount"),
                              p.get("actual_weighed_amount"), p.get("actual_final_volume"),
                              p.get("calculated_actual_concentration"), p.get("prepared_at"), p.get("operator")])
        write_sheet("配方与配制",
                    ["配方代码", "配方名称", "版本", "目标体积", "体积单位", "理论总量(g)", "纯度修正(g)",
                     "实际称量(g)", "实际定容", "反算浓度", "配制时间", "操作人"],
                    prep_rows,
                    note="组分明细快照见各配制记录下方展开表。")

        # 配制明细
        detail_rows = []
        for p in data["preparations"]:
            try:
                snapshot = json.loads(p.get("detail_snapshot") or "[]")
            except ValueError:
                snapshot = []
            for d in snapshot:
                detail_rows.append([p.get("formula_code"), p.get("version_no"), d.get("component_code"),
                                    d.get("component_name"), d.get("target_concentration"),
                                    d.get("concentration_unit"), d.get("source_type"),
                                    d.get("theoretical_amount_g"), d.get("corrected_amount_g"),
                                    d.get("stock_volume_ml")])
        write_sheet("配制组分明细",
                    ["配方代码", "版本", "组分代码", "组分名称", "目标浓度", "浓度单位", "来源",
                     "理论用量(g)", "纯度修正(g)", "母液体积(mL)"], detail_rows)

        # 补料计划
        plan = data["plan"] or {}
        write_sheet("补料计划",
                    ["计划版本", "状态", "阶段", "液体", "泵", "计划开始", "计划结束", "计划量(mL)",
                     "目标流速(mL/h)", "时长(h)", "事件状态", "备注"],
                    [[plan.get("version_no"), plan.get("status"), e.get("stage_name"), e.get("liquid_name"),
                      e.get("pump_code"), e.get("planned_start"), e.get("planned_end"),
                      e.get("planned_volume_ml"), e.get("target_flow_ml_h"), e.get("duration_h"),
                      e.get("status"), e.get("notes")] for e in data["events"]],
                    note="计划累计量按有效事件汇总；变更应创建新计划版本。")

        # 泵校准
        cal_rows = []
        for c in data["calibrations"]:
            for pt in c.get("points", []):
                cal_rows.append([c.get("pump_code"), c.get("calibration_date"), c.get("calibration_status"),
                                 c.get("calibration_method"), pt.get("setpoint_value"), pt.get("setpoint_unit"),
                                 pt.get("measured_flow"), pt.get("flow_unit"), pt.get("measured_volume"),
                                 pt.get("run_duration"), pt.get("duration_unit")])
        write_sheet("泵校准",
                    ["泵", "校准日期", "状态", "方法", "设置值", "设置值单位", "实测流速", "流速单位",
                     "实测体积", "运行时长", "时长单位"], cal_rows,
                    note="仅在实际测量点覆盖范围内插值；超出范围应重新校准或人工确认。")

        # 剂量核算
        write_sheet("剂量核算",
                    ["核算编号", "泵", "液体", "开始", "结束", "计划量(mL)", "累计差值(mL)", "流速积分(mL)",
                     "偏差(mL)", "偏差率(%)", "完成率(%)", "方法", "质量状态", "版本", "计算时间", "来源"],
                    [[c.get("calculation_id"), c.get("pump_code"), c.get("liquid_name"), c.get("time_start"),
                      c.get("time_end"), c.get("planned_volume_ml"), c.get("actual_volume_ml"),
                      c.get("flow_integral_ml"), c.get("deviation_ml"), c.get("deviation_percent"),
                      c.get("completion_percent"), c.get("calculation_method"), c.get("quality_status"),
                      c.get("calculation_version"), c.get("calculated_at"), c.get("value_source", "来源待核实")] for c in data["calculations"]])

        write_sheet("手工补料记录", ["记录编号", "泵", "液体", "计划事件", "开始", "结束", "开始读数", "结束读数", "单位", "中途读数", "计划量(mL)", "设备估算量(mL)", "估算偏差(mL)", "独立实测量(mL)", "实测方法", "实测偏差(mL)", "记录状态", "核查状态", "审核原因", "设备信息", "备注"],
                    [[m.get("record_id"), m.get("pump_code"), m.get("liquid_name"), m.get("event_id") or "计划外", m.get("start_time"), m.get("end_time"), m.get("start_reading"), m.get("end_reading"), m.get("reading_unit"), m.get("intermediate_readings"), m.get("planned_volume_ml"), m.get("estimate_ml"),
                      m["estimate_ml"] - m["planned_volume_ml"] if m.get("estimate_ml") is not None and m.get("planned_volume_ml") is not None else None,
                      m.get("measured_ml") if m.get("measured_ml") is not None else "未记录", m.get("measured_method"),
                      m["measured_ml"] - m["planned_volume_ml"] if m.get("measured_ml") is not None and m.get("planned_volume_ml") is not None else None,
                      m.get("lifecycle_status"), m.get("quality_status"), m.get("issues"), m.get("equipment_notes"), m.get("notes")] for m in data["manual"]],
                    note="设备估算量由 Dose Monitor 累计读数得到，独立实测量另行记录。")

        write_sheet("成品培养基", ["名称", "产品批号", "体积", "单位", "使用时间", "操作人", "备注"],
                    [[m['medium_name'], m['product_lot'], m['volume'], m['volume_unit'], m['used_at'], m['operator'], m['notes']] for m in data['commercial']])

        # 导入记录
        write_sheet("数据导入",
                    ["导入编号", "来源", "文件名", "导入时间", "总行数", "成功", "错误", "状态", "导入人"],
                    [[i.get("import_id"), i.get("source_type"), i.get("original_filename"), i.get("imported_at"),
                      i.get("row_count"), i.get("success_count"), i.get("error_count"), i.get("import_status"),
                      i.get("imported_by")] for i in data["imports"]])

        # 异常
        write_sheet("异常记录",
                    ["异常编号", "类型", "级别", "描述", "状态", "创建时间", "解决时间", "处理说明"],
                    [[a.get("anomaly_id"), a.get("anomaly_type"), a.get("severity"), a.get("description"),
                      a.get("status"), a.get("created_at"), a.get("resolved_at"), a.get("resolution_note")]
                     for a in data["anomalies"]])

        target = self._target_dir(batch["batch_code"]) / f"批次报告_{safe_name(batch['batch_code'])}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        wb.save(target)
        self._record(batch_id, "Excel", target, user)
        return target

    # ---------- PDF ----------
    def generate_pdf(self, batch_id: str, user: str) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise ReportError("缺少 reportlab，无法生成 PDF 报告") from exc

        font_name = self._register_cn_font(pdfmetrics, TTFont)
        data = self.collect(batch_id)
        batch = data["batch"]
        target = self._target_dir(batch["batch_code"]) / f"批次报告_{safe_name(batch['batch_code'])}_{datetime.now():%Y%m%d_%H%M%S}.pdf"

        styles = getSampleStyleSheet()
        title = ParagraphStyle("cn_title", parent=styles["Title"], fontName=font_name, fontSize=18, leading=26,
                               textColor=colors.HexColor("#1F4E79"), alignment=TA_CENTER, spaceAfter=10)
        h2 = ParagraphStyle("cn_h2", parent=styles["Heading2"], fontName=font_name, fontSize=13, leading=18,
                            textColor=colors.HexColor("#1F4E79"), spaceBefore=10, spaceAfter=6)
        body = ParagraphStyle("cn_body", parent=styles["BodyText"], fontName=font_name, fontSize=9, leading=13)
        small = ParagraphStyle("cn_small", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#666666"))

        doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                                topMargin=15 * mm, bottomMargin=15 * mm,
                                title=f"批次报告 {batch['batch_code']}", author=user)
        story = [Paragraph("细胞培养基配制与补料剂量核算报告", title),
                 Paragraph(f"批次编号：{batch['batch_code']}", ParagraphStyle("sub", parent=body, fontSize=12, alignment=TA_CENTER)),
                 Spacer(1, 8)]

        def table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None):
            content = [[Paragraph(str(h), body) for h in headers]]
            for row in rows:
                content.append([Paragraph("" if v is None else str(v), body) for v in row])
            t = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EAF1F8")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))

        meta = [
            ["项目名称", batch.get("project_name") or "", "培养体系", batch.get("culture_system") or ""],
            ["反应器", batch.get("reactor_code") or "", "工作体积 (mL)", fmt(batch.get("working_volume_ml"))],
            ["批次状态", batch.get("status") or "", "开始时间", batch.get("start_time") or ""],
            ["结束时间", batch.get("end_time") or "", "报告时间", now_iso()],
        ]
        table(["项目", "内容", "项目", "内容"], meta, [28 * mm, 55 * mm, 28 * mm, 55 * mm])
        story.append(Paragraph("一、批次概况", h2))
        summary = [
            ["培养阶段", len(data["stages"]), "培养参数", len(data["parameters"]), "配制记录", len(data["preparations"])],
            ["补料事件", len(data["events"]), "设备导入", len(data["imports"]), "剂量核算", len(data["calculations"])],
            ["异常记录", len(data["anomalies"]), "未解决异常", sum(1 for a in data["anomalies"] if a["status"] == "未解决"), "泵绑定", len(data["mappings"])],
        ]
        table(["项目", "数量", "项目", "数量", "项目", "数量"], summary,
              [30 * mm, 20 * mm, 30 * mm, 20 * mm, 30 * mm, 20 * mm])

        story.append(Paragraph("二、补料计划", h2))
        if data['commercial']:
            story.append(Paragraph("成品培养基使用记录", h2))
            table(["名称", "批号", "体积", "单位", "使用时间"], [[m['medium_name'], m['product_lot'] or '', m['volume'], m['volume_unit'], m['used_at']] for m in data['commercial']], [43*mm, 36*mm, 20*mm, 15*mm, 51*mm])
        if data["events"]:
            table(["阶段", "液体", "泵", "开始", "结束", "计划量(mL)", "流速(mL/h)", "状态"],
                  [[e.get("stage_name") or "", e.get("liquid_name") or "", e.get("pump_code") or "",
                    e.get("planned_start") or "", e.get("planned_end") or "", fmt(e.get("planned_volume_ml")),
                    fmt(e.get("target_flow_ml_h")), e.get("status") or ""] for e in data["events"]],
                  [22 * mm, 24 * mm, 18 * mm, 30 * mm, 30 * mm, 20 * mm, 20 * mm, 16 * mm])
        else:
            story.append(Paragraph("尚无补料计划事件。", body))

        story.append(Paragraph("三、剂量核算（累计差值与来源）", h2))
        if data["calculations"]:
            table(["泵", "液体", "计划量", "累计差", "流速积分", "偏差率", "完成率", "状态/来源"],
                  [[c.get("pump_code") or "", c.get("liquid_name") or "", fmt(c.get("planned_volume_ml")),
                    fmt(c.get("actual_volume_ml")), fmt(c.get("flow_integral_ml")),
                    fmt(c.get("deviation_percent")), fmt(c.get("completion_percent")), (c.get("quality_status") or "") + " / " + c.get("value_source", "来源待核实")]
                   for c in data["calculations"]], [18 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm, 18 * mm, 18 * mm, 20 * mm])
        else:
            story.append(Paragraph("尚无剂量核算结果。", body))

        story.append(Paragraph("手工补料记录（设备估算与独立实测）", h2))
        if data["manual"]:
            table(["泵 / 液体", "计划量 mL", "设备估算 mL", "独立实测 mL", "状态"],
                  [[f"{m['pump_code']} / {m['liquid_name']}", fmt(m.get('planned_volume_ml')),
                    fmt(m.get('estimate_ml')), fmt(m.get('measured_ml')) if m.get('measured_ml') is not None else '未记录',
                    m['lifecycle_status'] if m['lifecycle_status'] != '已完成' else m['quality_status']] for m in data['manual']], [40*mm, 30*mm, 35*mm, 35*mm, 25*mm])
            for m in data["manual"]:
                planned = m.get("planned_volume_ml")
                estimated = m.get("estimate_ml")
                measured = m.get("measured_ml")
                estimate_diff = fmt(estimated - planned) if estimated is not None and planned is not None else "不适用"
                measured_diff = fmt(measured - planned) if measured is not None and planned is not None else "不适用"
                story.append(Paragraph(f"{m['record_id']}：设备估算偏差 {estimate_diff} mL；独立实测偏差 {measured_diff} mL。", small))
        else:
            story.append(Paragraph("尚无手工补料记录。", body))

        story.append(Paragraph("四、异常记录", h2))
        if data["anomalies"]:
            table(["类型", "级别", "描述", "状态", "处理说明"],
                  [[a.get("anomaly_type") or "", a.get("severity") or "", (a.get("description") or "")[:120],
                    a.get("status") or "", (a.get("resolution_note") or "")[:80]] for a in data["anomalies"]],
                  [25 * mm, 15 * mm, 80 * mm, 18 * mm, 30 * mm])
        else:
            story.append(Paragraph("无异常记录。", body))

        story.append(Spacer(1, 10))
        story.append(Paragraph("说明：本报告由软件自动生成。标记为“估算”“待审核”或“无效”的结果不得作为唯一质量决策依据；"
                               "原始导入记录、人工修正记录和计算版本应一并保存。", small))
        doc.build(story)
        self._record(batch_id, "PDF", target, user)
        return target

    def _register_cn_font(self, pdfmetrics, TTFont) -> str:
        candidates = [
            (r"C:\Windows\Fonts\msyh.ttc", 0), (r"C:\Windows\Fonts\msyhbd.ttc", 0),
            (r"C:\Windows\Fonts\simhei.ttf", None), (r"C:\Windows\Fonts\simsun.ttc", 0),
        ]
        for path, index in candidates:
            if not Path(path).exists():
                continue
            try:
                kwargs = {} if index is None else {"subfontIndex": index}
                pdfmetrics.registerFont(TTFont("CNFont", path, **kwargs))
                return "CNFont"
            except Exception:
                continue
        return "Helvetica"

    # ---------- 称量清单 ----------
    def generate_weighing_list(self, preparation_id: str) -> Path:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        row = self.db.q1(
            "SELECT p.*, b.batch_code, f.formula_code, f.formula_name, f.version_no FROM preparation_record p "
            "JOIN formula_info f ON f.formula_id=p.formula_id LEFT JOIN batch_info b ON b.batch_id=p.batch_id "
            "WHERE p.preparation_id=?", (preparation_id,))
        if not row:
            raise ReportError("配制记录不存在")
        row = dict(row)
        details = json.loads(row.get("detail_snapshot") or "[]")
        wb = Workbook()
        ws = wb.active
        ws.title = "称量清单"
        ws["A1"] = f"称量清单 - {row.get('batch_code') or '未关联批次'} / {row['formula_code']} V{row['version_no']}"
        ws["A1"].font = Font(name="Microsoft YaHei", size=14, bold=True)
        ws["A2"] = f"目标体积：{row['target_volume']} {row['volume_unit']}    配制时间：{row.get('prepared_at') or ''}    操作人：{row.get('operator') or ''}"
        headers = ["序号", "组分代码", "组分名称", "目标浓度", "单位", "来源", "理论用量(g)", "纯度修正(g)", "母液体积(mL)"]
        ws.append([])
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=4, column=c)
            cell.font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E79")
            cell.alignment = Alignment(horizontal="center")
        for i, d in enumerate(details, 1):
            ws.append([i, d.get("component_code"), d.get("component_name"), d.get("target_concentration"),
                       d.get("concentration_unit"), d.get("source_type"), d.get("theoretical_amount_g"),
                       d.get("corrected_amount_g"), d.get("stock_volume_ml")])
        for col, width in {"A": 6, "B": 16, "C": 24, "D": 12, "E": 10, "F": 12, "G": 14, "H": 14, "I": 16}.items():
            ws.column_dimensions[col].width = width
        target = self._target_dir(row.get("batch_code") or "UNASSIGNED") / f"称量清单_{safe_name(row['formula_code'])}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        wb.save(target)
        return target
