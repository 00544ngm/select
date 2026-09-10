import { expect, it } from "vitest";
import {
  evidenceLevelLabel,
  formatKeywordDisplay,
  formatStrategy,
  relationLabel,
  deepArgumentKeyLabel,
  purchaseChainKeyLabel,
  decisionActionLabel,
  executionStatusLabel,
  rejectionCodeLabel,
} from "@/lib/result-labels";

it("renders relation enums as Chinese with the original English value", () => {
  expect(relationLabel("required_dependency")).toBe("必需依赖（required_dependency）");
});

it("renders evidence and decision statuses bilingually", () => {
  expect(evidenceLevelLabel("E1")).toBe("候选发现（E1）");
  expect(executionStatusLabel("hold")).toBe("待补证据后复核");
  expect(decisionActionLabel("priority_test")).toBe("优先测试（priority_test）");
  expect(rejectionCodeLabel("incompatible")).toBe(
    "已确认存在规格冲突（incompatible）"
  );
});

it("keeps pricing details while translating the strategy prefix", () => {
  expect(formatStrategy("bundled at $8-15")).toBe("组合定价（bundled at）$8-15");
  expect(formatStrategy("$19.99")).toBe("$19.99");
});

it("formats machine keys and search phrases for readable bilingual display", () => {
  expect(deepArgumentKeyLabel("purchase_chain")).toBe("购买链路（purchase_chain）");
  expect(purchaseChainKeyLabel("using_candidate")).toBe("使用辅品（using_candidate）");
  expect(formatKeywordDisplay({ amazon: "cat backpack carrier pet carrier backpack cat leash and harness set" }))
    .toContain("中文释义：猫咪背包运输包、宠物运输背包、猫咪牵引绳和背带套装");
});
