import { expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import JobError from "@/components/jobs/job-error";

it("explains an upstream account-group routing failure in Chinese", () => {
  render(
    <JobError
      errorCode="LLM_FAILED"
      errorMessage="Model is not supported by any configured account in this group"
    />
  );

  expect(screen.getByText("当前账户分组无法路由到所选模型")).toBeInTheDocument();
  expect(screen.getByText(/前往 API 设置重新验证/)).toBeInTheDocument();
  expect(screen.getByText(/技术详情/)).toBeInTheDocument();
});

it("tells another Windows user to re-enter an undecryptable API key", () => {
  render(
    <JobError
      errorCode="PROVIDER_CONFIG_DECRYPT_FAILED"
      errorMessage="The API key must be re-entered"
    />
  );

  expect(screen.getAllByText(/当前 Windows 用户/).length).toBeGreaterThan(0);
  expect(screen.getByText(/重新输入 API Key/)).toBeInTheDocument();
});

it("offers recovery and diagnostics for a closed packaged browser", () => {
  render(
    <JobError
      errorCode="BROWSER_TARGET_CLOSED"
      errorMessage="商品浏览器意外关闭"
      onRetry={() => undefined}
    />
  );

  expect(screen.getByText("商品浏览器已意外关闭")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "自动修复后重试" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "运行环境检查" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "打开日志目录" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "打开 Windows 安全中心" })).toBeInTheDocument();
});

it.each([
  ["PROVIDER_AUTH_FAILED", "API Key 无效"],
  ["PROVIDER_PERMISSION_DENIED", "没有所选模型的访问权限"],
  ["PROVIDER_MODEL_INVALID", "模型不存在或当前不可用"],
  ["PROVIDER_PROTOCOL_MISMATCH", "接口协议不匹配"],
  ["PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED", "结构化输出模式不受支持"],
  ["PROVIDER_REQUEST_TOO_LARGE", "请求内容超过服务限制"],
  ["PROVIDER_RATE_LIMITED", "模型服务正在限流"],
  ["PROVIDER_UPSTREAM_UNAVAILABLE", "上游模型服务暂时不可用"],
  ["PROVIDER_MODEL_TASK_TIMEOUT", "模型报告生成超时"],
  ["PROVIDER_CONNECTION_FAILED", "无法连接模型服务"],
  ["PROVIDER_EMPTY_RESPONSE", "模型返回了空内容"],
  ["MODEL_INVALID_JSON", "模型报告格式不完整"],
])("explains stable provider error %s", (errorCode, title) => {
  render(<JobError errorCode={errorCode} errorMessage="safe technical detail" />);

  expect(screen.getByText(title)).toBeInTheDocument();
});

it("gives OpenAI-compatible endpoint advice for a protocol mismatch", () => {
  render(
    <JobError
      errorCode="PROVIDER_PROTOCOL_MISMATCH"
      errorMessage="endpoint not found"
    />
  );

  expect(screen.getByText(/\/v1\/chat\/completions 或 \/v1\/responses/)).toBeInTheDocument();
});

it("asks the user to reverify when structured output modes are unsupported", () => {
  render(
    <JobError
      errorCode="PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED"
      errorMessage="response_format is unsupported"
    />
  );

  expect(screen.getByText(/重新验证模型/)).toBeInTheDocument();
});

it.each([
  ["WALMART_NAVIGATION_TIMEOUT", "Walmart 页面加载超时"],
  ["WALMART_NETWORK_FAILED", "无法连接 Walmart"],
  ["WALMART_CAPTCHA_TIMEOUT", "Walmart 人工验证未完成"],
])("explains stable Walmart scrape error %s", (errorCode, title) => {
  render(
    <JobError
      errorCode={errorCode}
      errorMessage="Page.goto: Timeout 30000ms exceeded at https://www.walmart.com/ip/private"
    />
  );

  expect(screen.getByText(title)).toBeInTheDocument();
  expect(
    screen.queryByText(/Page\.goto: Timeout 30000ms exceeded/)
  ).not.toBeInTheDocument();
});
