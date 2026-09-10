# Anthropic-Compatible Custom Provider Design

## Goal

Extend the existing custom API provider so users can select either the OpenAI-compatible protocol or the Anthropic Messages API protocol. The integration must follow the supplied `anthropic_chat.py` reference for connection configuration and request semantics while preserving every existing provider and analysis workflow.

## Scope

This change covers provider configuration, encrypted persistence, connection testing, runtime client resolution, structured output, model selection, retry behavior, frontend settings, and end-to-end validation. It does not change scraping, prompts, analysis scoring, result schemas, historical results, or the fixed OpenAI, CatToken, and DeepSeek protocols.

## User Experience

The custom API settings panel adds an `API protocol` segmented control with two values:

- `OpenAI compatible` preserves the current `/chat/completions` behavior.
- `Anthropic compatible` uses the Anthropic Messages API at `/v1/messages`.

Both protocols share the existing service name, base URL, API key, default model, and enabled state fields. The base URL is the provider service root, for example `https://api.anthropic.com`; users do not append `/v1/messages`. The official SDK constructs the endpoint path and protocol headers.

Changing the protocol clears the current successful-test state in the form and requires a new connection test before the changed configuration can be enabled and saved. The API key remains masked in the browser and encrypted at rest.

## Persistence And Compatibility

Add an `api_protocol` column to `provider_configurations`, constrained in application code to `openai` or `anthropic`. The migration gives all existing rows the value `openai`, preserving current behavior without requiring users to reconfigure providers.

Only the custom provider accepts a user-selected protocol. Fixed providers continue to expose their existing protocol and cannot be changed through the UI. Public provider responses include `api_protocol`; secrets and authorization headers remain excluded.

Historical jobs and results require no migration. A job continues to store the custom provider slug and selected model. At execution time the worker loads the saved provider configuration, including its protocol, and resolves the matching client.

## Backend Architecture

`ProviderRuntimeConfig` carries the resolved protocol from the database to connection testing and runtime client construction. The provider resolver chooses the client by protocol for the custom provider:

- `openai` builds the existing OpenAI-compatible client.
- `anthropic` builds a new asynchronous Anthropic-compatible client.

OpenAI, CatToken, and DeepSeek retain their current client selection rules. A retry preserves the original provider, protocol, and model and never silently falls back to another provider.

The Anthropic client follows the supplied reference implementation:

- Initialize the official asynchronous Anthropic SDK with `api_key`, `base_url`, and timeout.
- Call `messages.create` with `model`, `max_tokens`, `messages`, and an optional separate `system` value.
- Normalize application messages so system messages become the Anthropic `system` parameter, while user and assistant messages remain in `messages`.
- Return the concatenated text from all text content blocks.
- Keep credentials only in process memory while making requests.

Streaming is not needed for the background analysis worker because the current application consumes complete responses. Using the non-streaming Messages API preserves the reference protocol while matching the existing service interface.

## Connection Testing And Models

A successful connection test always requires a real text-generation request:

- OpenAI-compatible custom providers call `chat.completions.create`.
- Anthropic-compatible custom providers call `messages.create` with a minimal `Reply OK` prompt.

The tester verifies that the response contains text. Authentication, permission, model-not-found, rate-limit, timeout, network, and upstream service errors map to the existing provider error contract without exposing credentials.

Anthropic-compatible services are not required to expose an OpenAI-style model-list endpoint. When model discovery is unavailable but the configured model successfully generates text, the test returns the configured model as the verified model. This makes it selectable and persistable without claiming that other models are supported. OpenAI-compatible discovery remains unchanged.

Saving an enabled configuration performs the same real connection test. The verified model list is persisted and becomes the source for the workbench model selector.

## Structured Output

The analysis services retain their existing JSON schemas and result parsing. For Anthropic-compatible execution, the client:

1. Combines existing system instructions with a JSON-only instruction containing the requested schema.
2. Sends that combined text through Anthropic's separate `system` parameter.
3. Sends user and assistant content through Messages API-compatible message objects.
4. Concatenates returned text blocks.
5. Parses a plain JSON object while tolerating a single Markdown JSON fence.

Empty responses and invalid JSON use the current bounded retry policy. After the final attempt, the task fails with the real reason and retains its selected provider and model. It never manufactures an empty result or switches protocols.

## Frontend Data Flow

Frontend provider types, form validation, payload builders, and API responses add `api_protocol`. The field is shown only for the custom provider. Existing provider tabs and workbench selection remain unchanged.

The settings flow is:

1. Select custom API.
2. Select OpenAI-compatible or Anthropic-compatible protocol.
3. Enter service name, base URL, API key, and model.
4. Run a real connection test.
5. Select the verified model when applicable.
6. Enable and save.
7. Select custom API and the verified model in the workbench.

Test and save errors use the existing inline error surface. Protocol changes invalidate any success message and model list held only by the current form until retested.

## Security And Logging

- API keys continue to use the existing encrypted database storage.
- Public API responses return only masked key metadata.
- Logs may record provider slug, protocol, model, HTTP status, and exception class.
- Logs must not record API keys, authorization headers, `x-api-key` headers, or decrypted provider records.
- The official Anthropic SDK owns `x-api-key` and `anthropic-version` header construction.

## Testing

Implementation follows test-driven development. Required automated coverage includes:

- Database migration defaults existing providers to `openai`.
- Provider schemas and repository round-trip `api_protocol`.
- Custom OpenAI-compatible behavior remains unchanged.
- Anthropic connection tests send a real Messages API request and require text.
- Anthropic tests return the configured model when discovery is unsupported.
- Anthropic client converts system messages and extracts multiple text blocks.
- Anthropic structured output parses plain and fenced JSON and reports empty or invalid responses.
- Resolver builds the correct client from the saved protocol.
- Retry preserves provider, protocol configuration, and model.
- Frontend settings render and submit the protocol selector.
- Changing protocols invalidates stale test success in the form.
- Workbench uses the verified custom model.
- Existing backend and frontend suites continue to pass.

End-to-end acceptance requires a real user-supplied Anthropic-compatible endpoint:

1. Configure custom API with Anthropic protocol, base URL, API key, and model.
2. Test successfully and save the verified model.
3. Run a new workbench task using that custom provider.
4. Verify provider and model remain custom/selected, progress reaches 100%, complete results render, and history contains the successful task.

## Delivery And Rollback

Implementation is split into reviewable commits: database and contracts, Anthropic client and connection test, frontend settings, and end-to-end verification. The existing OpenAI-compatible custom provider remains available throughout. Each implementation stage can be reverted independently, and this design commit contains no runtime changes.
