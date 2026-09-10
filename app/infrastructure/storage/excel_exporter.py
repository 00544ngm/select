"""Excel export for A+B Bundling results."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.domain.dto import HypothesisDTO, HypothesisResultDTO, JudgmentResultDTO

HYPOTHESIS_DIRECTION_COLUMNS = (
    "模型版本", "方向名称", "品类", "动机类型", "动机证据", "证据等级",
    "1688预估成本", "定价策略", "粘性", "预估评分", "最终评分", "粘性评分",
    "当前处理建议", "具体原因", "下一步",
    "购买方向", "购买方向依据", "产品类型状态", "执行状态", "待验证原因",
    "最终动作", "原始计算分", "分数上限", "推荐等级", "主要关系", "消费者模拟",
    "淘汰状态", "淘汰原因", "食品过滤", "食品过滤说明", "功能必要性",
    "使用连续性", "购买方向评分", "场景一致性", "增强维护保护", "自然联购",
    "市场证据状态", "关系强度", "生命周期连接", "持续使用或复购", "功能增益",
    "市场证据", "用户与场景", "关系理由", "购买链路", "拓展场景", "成立前提",
    "可信度", "英文关键词", "亚马逊搜索词", "用户理性", "卖家理性", "紧迫性",
    "差异化", "风险缓释", "场景适配", "组合展示", "Listing卖点", "定价策略说明",
    "上架行动项",
)


def _employee_guidance(hypothesis: HypothesisDTO) -> tuple[str, str, str]:
    """Translate technical decision fields into employee-facing action language."""
    missing_evidence = next(
        (
            str(item).strip()
            for item in [*hypothesis.missing_evidence, *hypothesis.hold_reasons]
            if str(item).strip()
        ),
        "",
    )
    if hypothesis.execution_status == "hold":
        reason = missing_evidence or "当前兼容、安全或产品信息尚未核实完整。"
        next_step = (
            f"请核对：{missing_evidence}"
            if missing_evidence
            else "补齐缺失证据后重新评估。"
        )
        return "补充证据后复核", reason, next_step

    if hypothesis.execution_status == "reject":
        reason = next(
            (
                value.strip()
                for value in (
                    hypothesis.incompatibility_reason,
                    hypothesis.duplicate_function_reason,
                    hypothesis.safety_risk,
                    hypothesis.food_filter_reason,
                )
                if value.strip()
            ),
            "",
        )
        if not reason or not hypothesis.source_fact_ids:
            return (
                "历史判定证据不完整",
                "旧结果缺少完整的阻断理由或事实来源。",
                "建议按新规则重新分析。",
            )
        return (
            "当前方案暂不进入测试",
            reason,
            "更换具体候选商品或解除上述阻断后重新分析。",
        )

    return (
        "可进入测试",
        hypothesis.direction_reason or "当前未发现确定阻断。",
        "按最终测试等级执行，并继续核对具体商品规格。",
    )


def _judgment_product_names(result: JudgmentResultDTO) -> list[str]:
    names: dict[str, None] = {}
    for item in result.alignment_review:
        name = str(item.get("product_b", "")).strip()
        if name:
            names[name] = None
    for section in (
        result.motivation_review,
        result.price_calculation,
        result.veto_check,
        result.c_score,
        result.b_score,
        result.delivery_package,
    ):
        for name in section.get("per_b_product", {}):
            if str(name).strip():
                names[str(name)] = None
    return list(names)


def export_hypothesis_to_excel(result: HypothesisResultDTO, filepath: str | Path | None = None) -> Path:
    """Export hypothesis generation results to Excel. Returns the file path."""
    if filepath is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = Path("output/bundling") / f"hypothesis_{timestamp}.xlsx"
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    rejection_summary = "; ".join(
        f"{code}: {count}"
        for code, count in sorted(result.rejection_summary.items())
    )
    actionable = (
        result.result_status == "completed_with_qualified_candidates"
        and any(
            direction.hypothesis.execution_status == "pass"
            and direction.hypothesis.decision_action
            in {"small_batch_test", "priority_test", "focus_development"}
            for direction in result.directions
        )
    )
    df_result_summary = pd.DataFrame(
        [
            {"字段": "结果状态", "值": result.result_status},
            {"字段": "结果说明", "值": result.result_message},
            {"字段": "模型版本", "值": result.model_version},
            {"字段": "供应商", "值": result.provider},
            {"字段": "实际模型", "值": result.provider_model},
            {"字段": "初次候选数", "值": result.initial_raw_direction_count},
            {"字段": "复核候选数", "值": result.audit_raw_direction_count},
            {"字段": "合格数量", "值": result.qualified_direction_count},
            {"字段": "待补证据数量", "值": result.hold_direction_count},
            {"字段": "淘汰数量", "值": result.rejected_direction_count},
            {"字段": "遗漏复核结果", "值": result.audit_outcome},
            {"字段": "淘汰原因汇总", "值": rejection_summary},
            {
                "字段": "是否可用于采购决策",
                "值": "可进入采购测试" if actionable else "不可直接采购",
            },
        ]
    )

    # Product Info
    product_data = {
        "字段": ["标题", "价格", "评分", "评论数", "买家画像", "使用场景", "随附清单"],
        "值": [
            result.product.title,
            result.product.price,
            result.product.rating,
            result.product.review_count,
            result.product_analysis.get("buyer_profile", ""),
            result.product_analysis.get("usage_scenario", ""),
            result.product_analysis.get("whats_included", ""),
        ],
    }
    df_product = pd.DataFrame(product_data)

    # Sheet 2: Strategic Judgment + Evidence
    evidence = result.evidence_table
    evidence_rows = []
    for layer_key in ["first_layer", "second_layer", "third_layer"]:
        layer = evidence.get(layer_key, {})
        for item_key, items in layer.items():
            if isinstance(items, list):
                for item in items:
                    evidence_rows.append({"证据层": layer_key, "类别": item_key, "内容": item})
    df_evidence = pd.DataFrame(evidence_rows) if evidence_rows else pd.DataFrame()

    # Strategic judgment
    sj = result.strategic_judgment
    df_judgment = pd.DataFrame([
        {"类型": sj.get("type", ""), "理由": sj.get("rationale", "")}
    ])

    # Sheet 3: Directions
    dir_rows = []
    for d in result.directions:
        h = d.hypothesis
        deep = d.deep_arguments
        checklist = d.delivery_checklist
        employee_action, employee_reason, employee_next_step = _employee_guidance(h)
        dir_rows.append({
            "模型版本": h.model_version,
            "方向名称": h.direction_name,
            "品类": h.category_type,
            "动机类型": h.motivation_type,
            "动机证据": h.motivation_evidence,
            "证据等级": h.evidence_level,
            "1688预估成本": h.estimated_cost_1688,
            "定价策略": h.price_strategy,
            "粘性": h.stickiness,
            "预估评分": h.estimated_score,
            "最终评分": h.final_score,
            "粘性评分": h.stickiness_score or h.final_score,
            "当前处理建议": employee_action,
            "具体原因": employee_reason,
            "下一步": employee_next_step,
            "购买方向": h.purchase_direction,
            "购买方向依据": h.direction_reason,
            "产品类型状态": h.product_type_status,
            "兼容性门禁": h.compatibility_status,
            "重复功能门禁": h.duplication_status,
            "安全性门禁": h.safety_status,
            "兼容性说明": h.incompatibility_reason,
            "重复功能说明": h.duplicate_function_reason,
            "安全性说明": h.safety_risk,
            "来源事实": "；".join(h.source_fact_ids),
            "执行状态": h.execution_status,
            "待验证原因": "；".join(h.hold_reasons),
            "最终动作": h.decision_action,
            "原始计算分": h.raw_score,
            "分数上限": h.score_cap,
            "推荐等级": h.recommendation_level,
            "主要关系": h.primary_relation,
            "消费者模拟": h.consumer_simulation,
            "淘汰状态": "是" if h.rejected else "否",
            "淘汰原因": "；".join(h.rejection_codes),
            "食品过滤": h.food_filter_status,
            "食品过滤说明": h.food_filter_reason,
            "功能必要性": h.score_breakdown.get(
                "function_necessity", h.score_breakdown.get("relation_strength", "")
            ),
            "使用连续性": h.score_breakdown.get(
                "usage_continuity", h.score_breakdown.get("lifecycle_connection", "")
            ),
            "购买方向评分": h.score_breakdown.get("purchase_direction", ""),
            "场景一致性": h.score_breakdown.get(
                "scene_fit", h.score_breakdown.get("user_scene", "")
            ),
            "增强维护保护": h.score_breakdown.get(
                "enhancement_maintenance", h.score_breakdown.get("function_gain", "")
            ),
            "自然联购": h.score_breakdown.get(
                "natural_copurchase", h.score_breakdown.get("mental_copurchase", "")
            ),
            "市场证据状态": h.evidence.get("market", {}).get("status", "待验证"),
            "关系强度": h.score_breakdown.get("relation_strength", ""),
            "生命周期连接": h.score_breakdown.get("lifecycle_connection", ""),
            "持续使用或复购": h.score_breakdown.get("repeat_value", ""),
            "功能增益": h.score_breakdown.get("function_gain", ""),
            "市场证据": h.score_breakdown.get("market_evidence", ""),
            "用户与场景": h.score_breakdown.get("user_scene", ""),
            "关系理由": "；".join(h.relation_reasons),
            "购买链路": " → ".join(h.purchase_chain.values()),
            "拓展场景": "；".join(
                str(item.get("name", item)) if isinstance(item, dict) else str(item)
                for item in h.extended_scenarios
            ),
            "成立前提": "；".join(h.assumptions),
            "可信度": h.confidence_level,
            "英文关键词": h.keywords.get("en", ""),
            "亚马逊搜索词": h.keywords.get("amazon", ""),
            "用户理性": deep.get("user_rationale", ""),
            "卖家理性": deep.get("seller_rationale", ""),
            "紧迫性": deep.get("urgency", ""),
            "差异化": deep.get("differentiation", ""),
            "风险缓释": deep.get("risk_mitigation", ""),
            "场景适配": deep.get("scenario_fit", ""),
            "组合展示": checklist.get("bundling_display", ""),
            "Listing卖点": checklist.get("listing_highlights", ""),
            "定价策略说明": checklist.get("pricing_tactic", ""),
            "上架行动项": "; ".join(checklist.get("launch_actions", [])),
        })
    if not dir_rows:
        status_row = {column: "" for column in HYPOTHESIS_DIRECTION_COLUMNS}
        status_row.update(
            {
                "模型版本": result.model_version,
                "方向名称": "未发现合格候选",
                "执行状态": result.result_status,
                "淘汰原因": rejection_summary,
            }
        )
        dir_rows.append(status_row)
    df_directions = pd.DataFrame(dir_rows, columns=HYPOTHESIS_DIRECTION_COLUMNS)

    # Sheet 4: Keywords
    df_keywords = pd.DataFrame({"关键词": result.keyword_pack})

    # Write to Excel
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df_result_summary.to_excel(writer, sheet_name="结果摘要", index=False)
        df_product.to_excel(writer, sheet_name="商品信息", index=False)
        df_judgment.to_excel(writer, sheet_name="战略判断", index=False)
        if not df_evidence.empty:
            df_evidence.to_excel(writer, sheet_name="证据表", index=False)
        df_directions.to_excel(writer, sheet_name="辅品方向", index=False)
        df_keywords.to_excel(writer, sheet_name="关键词包", index=False)

    return filepath


def export_judgment_to_excel(result: JudgmentResultDTO, filepath: str | Path | None = None) -> Path:
    """Export judgment results to Excel. Returns the file path."""
    if filepath is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = Path("output/bundling") / f"judgment_{timestamp}.xlsx"
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    b_names = _judgment_product_names(result)

    # Sheet 1: Overview
    ov_rows = []
    for name in b_names:
        veto = result.veto_check.get("per_b_product", {}).get(name, {})
        delivery = result.delivery_package.get("per_b_product", {}).get(name, {})
        c_total = result.c_score.get("per_b_product", {}).get(name, {}).get("total", 0)
        b_total = result.b_score.get("per_b_product", {}).get(name, {}).get("total", 0)
        ov_rows.append({
            "B品": name,
            "C组合分": c_total,
            "B跨境分": b_total,
            "是否否决": "是" if veto.get("vetoed") else "否",
            "否决原因": veto.get("veto_reason", ""),
            "推荐捆绑方式": delivery.get("recommended_bundle_type", ""),
            "上架优先级": delivery.get("launch_priority", ""),
        })
    if not ov_rows:
        ov_rows.append({"B品": ""})
    for index, row in enumerate(ov_rows):
        row["整体判级"] = result.final_grade if index == 0 else ""
        row["综合评分"] = result.priority_score if index == 0 else ""
    df_overview = pd.DataFrame(ov_rows)
    overview_columns = ["整体判级", "综合评分"] + [
        column
        for column in df_overview.columns
        if column not in {"整体判级", "综合评分"}
    ]
    df_overview = df_overview[overview_columns]

    # Sheet 2: Alignment review
    align_rows = []
    for a in result.alignment_review:
        align_rows.append({
            "B品": a.get("product_b", ""),
            "原假设": a.get("original_hypothesis", ""),
            "规格匹配": a.get("spec_match", ""),
            "价格对齐": a.get("price_alignment", ""),
            "功能互补": a.get("function_complement", ""),
            "尺寸适配": a.get("size_fit", ""),
            "结论": a.get("overall_verdict", ""),
        })
    df_align = pd.DataFrame(align_rows)

    # Sheet 3: Price calculation
    price_rows = []
    for name in b_names:
        p = result.price_calculation.get("per_b_product", {}).get(name, {})
        price_rows.append({
            "B品": name,
            "A品价格": p.get("a_price", ""),
            "B品价格": p.get("b_price", ""),
            "组合价格": p.get("combined_price", ""),
            "建议捆绑价": p.get("suggested_bundle_price", ""),
            "1688成本": p.get("b_1688_cost", ""),
            "毛利评估": p.get("margin_assessment", ""),
        })
    df_price = pd.DataFrame(price_rows)

    # Sheet 4: Detailed scoring
    score_rows = []
    for name in b_names:
        c = result.c_score.get("per_b_product", {}).get(name, {})
        b = result.b_score.get("per_b_product", {}).get(name, {})
        score_rows.append({
            "B品": name,
            "C-互补强度": c.get("complementarity", 0),
            "C-客单价提升": c.get("ticket_lift", 0),
            "C-场景增值": c.get("scenario_value", 0),
            "C-差评覆盖": c.get("pain_point_coverage", 0),
            "C-总分": c.get("total", 0),
            "B-供给成熟度": b.get("supply_maturity", 0),
            "B-物流友好": b.get("logistics_friendliness", 0),
            "B-认证门槛": b.get("certification_barrier", 0),
            "B-旺季窗口": b.get("season_window", 0),
            "B-总分": b.get("total", 0),
        })
    df_scores = pd.DataFrame(score_rows) if score_rows else pd.DataFrame()

    # Sheet 5: Delivery package
    delivery_rows = []
    for name in b_names:
        d = result.delivery_package.get("per_b_product", {}).get(name, {})
        delivery_rows.append({
            "B品": name,
            "推荐捆绑": d.get("recommended_bundle_type", ""),
            "定价策略": d.get("pricing_tactic", ""),
            "Listing方案": d.get("listing_collateral", ""),
            "优先级": d.get("launch_priority", ""),
            "下一步": "; ".join(d.get("next_steps", [])),
        })
    df_delivery = pd.DataFrame(delivery_rows)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df_overview.to_excel(writer, sheet_name="判级概览", index=False)
        df_align.to_excel(writer, sheet_name="对齐审查", index=False)
        df_price.to_excel(writer, sheet_name="价格计算", index=False)
        if not df_scores.empty:
            df_scores.to_excel(writer, sheet_name="评分明细", index=False)
        df_delivery.to_excel(writer, sheet_name="交付清单", index=False)

    return filepath


__all__ = ["export_hypothesis_to_excel", "export_judgment_to_excel"]
