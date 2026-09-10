class AppError(Exception):
    """Base exception for the application."""


class ConfigError(AppError):
    """Raised when configuration is invalid."""


class BrowserError(AppError):
    """Raised on browser automation failures."""


class BrowserTargetClosedError(BrowserError):
    code = "BROWSER_TARGET_CLOSED"
    retryable = True

    def __init__(self) -> None:
        self.message = (
            "商品浏览器意外关闭，软件已自动重启并重试一次但仍未恢复；"
            "请运行环境检查，并查看 Windows 安全中心和日志目录。"
        )
        super().__init__(self.message)


class WalmartSearchError(AppError):
    """Raised when Walmart search fails."""


class ParseError(AppError):
    """Raised when parsing page content fails."""


class RetryExhaustedError(AppError):
    """Raised when all retry attempts are exhausted."""


class LLMError(AppError):
    """Raised when LLM (GPT) calls fail."""


class LLMTaskTimeoutError(LLMError):
    """Raised when a report-sized model request exceeds its safe deadline."""

    code = "PROVIDER_MODEL_TASK_TIMEOUT"
    retryable = False

    def __init__(self, *, model: str, timeout_seconds: int) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.message = (
            f"模型 {model} 在 {timeout_seconds} 秒内未完成完整报告。"
            "系统已停止自动重试，避免重复消耗；请改用已通过完整报告测试的模型 "
            "gpt-5.4，或重新验证其他模型。"
        )
        super().__init__(self.message)


class ScrapeError(AppError):
    """Raised when product scraping fails."""


class WalmartCaptchaRequiredError(ScrapeError):
    """Internal signal that Walmart requires interactive verification."""


class WalmartCaptchaTimeoutError(ScrapeError):
    code = "WALMART_CAPTCHA_TIMEOUT"
    retryable = True

    def __init__(self) -> None:
        self.message = (
            "Walmart 要求人工验证，但未在限定时间内完成；本次未抓取到商品数据，"
            "模型尚未调用；请重新提交并在弹出的 Walmart 窗口中完成验证。"
        )
        super().__init__(self.message)


class WalmartNavigationTimeoutError(ScrapeError):
    """Raised when Walmart product navigation exceeds the configured deadline."""

    code = "WALMART_NAVIGATION_TIMEOUT"
    retryable = True

    def __init__(self) -> None:
        self.message = "Walmart 商品页面加载超时，请检查网络、代理或稍后重试"
        super().__init__(self.message)


class WalmartNetworkError(ScrapeError):
    """Raised when the browser cannot establish a Walmart navigation connection."""

    code = "WALMART_NETWORK_FAILED"
    retryable = True

    def __init__(self) -> None:
        self.message = "无法连接 Walmart，请检查网络、代理或安全软件后重试"
        super().__init__(self.message)


class UnsupportedPlatformError(AppError):
    """Raised when a product URL does not belong to a supported platform."""


class ScrapeIncompleteError(ScrapeError):
    """Raised when scraping omits fields required for analysis."""


class ModelContractError(AppError):
    code = "MODEL_CONTRACT_MISMATCH"
    retryable = False

    def __init__(self, *, expected: str, actual: str | None) -> None:
        self.expected = expected
        self.actual = actual
        self.message = (
            f"Model contract mismatch: expected {expected}, got {actual or 'missing'}. "
            "Restart the API and Worker before retrying."
        )
        super().__init__(self.message)


class ProductTypeGateError(AppError):
    retryable = False

    def __init__(self, *, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(self.message)


__all__ = [
    "AppError",
    "BrowserError",
    "BrowserTargetClosedError",
    "ConfigError",
    "LLMError",
    "LLMTaskTimeoutError",
    "ModelContractError",
    "ParseError",
    "ProductTypeGateError",
    "RetryExhaustedError",
    "ScrapeError",
    "ScrapeIncompleteError",
    "UnsupportedPlatformError",
    "WalmartCaptchaRequiredError",
    "WalmartCaptchaTimeoutError",
    "WalmartNavigationTimeoutError",
    "WalmartNetworkError",
    "WalmartSearchError",
]
