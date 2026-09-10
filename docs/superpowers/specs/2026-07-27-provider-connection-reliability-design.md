# Provider Connection Reliability Design

## Problem

CatToken connection checks are intermittent: successful requests can take longer than the current five-second timeout, and the upstream sometimes returns HTTP 502. The UI currently collapses both cases into an unhelpful reachability error or a generic internal error.

## Approved Design

- Keep CatToken's application base URL as `https://www.cattoken.vip/v1`; this application uses OpenAI Chat Completions, unlike the Codex CLI `responses` configuration.
- Configure the OpenAI SDK connection-test client with a 30-second timeout and two retries. Authentication, permission, and invalid-model responses remain non-retryable SDK errors.
- Map HTTP 5xx responses to a provider-specific Chinese upstream-unavailable message.
- Map timeouts and connection failures to a provider-specific Chinese network/reachability message.
- Preserve the existing error codes and HTTP behavior so frontend contracts do not change.

## Verification

- Unit tests assert the timeout and retry configuration.
- Unit tests assert that HTTP 502 and connection failures produce distinct messages.
- Full backend tests verify no regressions.

