import { expect, it } from "vitest";
import {
  beijingDateKey,
  formatBeijingTime,
  formatDuration,
} from "@/lib/job-time";

it("uses Asia/Shanghai for display and date grouping", () => {
  expect(formatBeijingTime("2026-07-27T13:37:06Z")).toBe("21:37");
  expect(beijingDateKey("2026-07-27T16:30:00Z")).toBe("2026-07-28");
});

it("formats duration and invalid values explicitly", () => {
  expect(
    formatDuration("2026-07-27T13:37:06Z", "2026-07-27T14:09:23Z")
  ).toBe("32分17秒");
  expect(formatDuration("invalid", "2026-07-27T14:09:23Z")).toBe(
    "时间不可用"
  );
});
