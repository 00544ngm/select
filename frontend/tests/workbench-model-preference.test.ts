import { beforeEach, describe, expect, it } from "vitest";
import {
  readWorkbenchModelPreference,
  writeWorkbenchModelPreference,
} from "@/lib/workbench-model-preference";

describe("workbench model preferences", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("stores each workbench entry independently with a version", () => {
    writeWorkbenchModelPreference("hypothesis", {
      provider: "custom",
      model: "custom-model",
    });
    writeWorkbenchModelPreference("judgment", {
      provider: "openai",
      model: "gpt-5.5",
    });

    expect(readWorkbenchModelPreference("hypothesis")).toEqual({
      version: 1,
      provider: "custom",
      model: "custom-model",
    });
    expect(readWorkbenchModelPreference("judgment")).toEqual({
      version: 1,
      provider: "openai",
      model: "gpt-5.5",
    });
    expect(readWorkbenchModelPreference("batch")).toBeNull();
  });

  it.each(["cattoken", "cattoken_claude"])(
    "rejects retired provider preference %s",
    (provider) => {
      localStorage.setItem(
        "workbench-model-preference:hypothesis",
        JSON.stringify({ version: 1, provider, model: "retired-model" })
      );

      expect(readWorkbenchModelPreference("hypothesis")).toBeNull();
      expect(
        localStorage.getItem("workbench-model-preference:hypothesis")
      ).toBeNull();
    }
  );

  it.each([
    "not-json",
    JSON.stringify({ version: 2, provider: "openai", model: "gpt-5.5" }),
    JSON.stringify({ version: 1, provider: "unknown", model: "gpt-5.5" }),
    JSON.stringify({ version: 1, provider: "openai" }),
  ])("ignores malformed or unsupported stored data", (stored) => {
    localStorage.setItem("workbench-model-preference:hypothesis", stored);
    expect(readWorkbenchModelPreference("hypothesis")).toBeNull();
  });
});
