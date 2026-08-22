# FlowForge AI — AI Diagnostics Architecture & Prompt Design

This document defines the architecture, failure diagnostics workflow, failsafe mechanisms, prompt designs, and hosting interfaces for the **AI Diagnostics Plane** in **FlowForge AI**.

---

## 1. Purpose
The AI Diagnostics Plane is an out-of-band analysis system that runs when background tasks permanently fail or route to the Dead Letter Queue (DLQ). It analyzes raw task stdout, stderr, and metadata to identify failure causes and suggest actionable fixes without impacting scheduling latency or transactional safety.

---

## 2. Failure Diagnostics Workflow

The diagnostics pipeline is executed completely asynchronously and decoupled from the main execution/scheduling path:

```
[Job Transitions to FAILED/DLQ]
             ↓
[Event Trigger: DiagnosticStateManager] ──> Status: NOT_REQUESTED
             ↓
[FastAPI Background Task Spawned]       ──> Status: ANALYZING
             ↓
[Retrieve Context: Logs + Metadata]
             ↓
[Execute Client: LLM Host Call]
             ↓
   ┌─────────┴─────────┐
   ▼ Success           ▼ Failure / Timeout
[Format Analysis]   [Fallback Template]
   ↓                   ↓
Status: COMPLETED   Status: FAILED / UNAVAILABLE
   ↓                   ↓
[Write to ai_diagnostics Table in PostgreSQL]
```

### Step-by-Step Execution Sequence
1. **Trigger**: When a job transitions to a terminal failure state (`FAILED` or `DLQ`), the `DiagnosticStateManager` registers a row in the `ai_diagnostics` table with `diagnostic_status = 'NOT_REQUESTED'`.
2. **Task Queueing**: A non-blocking asynchronous event is spawned (via FastAPI's `BackgroundTasks` or an internal asyncio loop) to run the analysis, setting `diagnostic_status = 'ANALYZING'`.
3. **Context Assembly**: The `AIDiagnosticsEngine` queries PostgreSQL to retrieve:
   - Sanitized job logs (truncated to 100 KB limit).
   - Target handler name, payload, and retry counts.
   - Database exit code, execution timestamps, and queue configuration.
4. **LLM Invocation**: The context is injected into the structured Prompt Template and dispatched to the decoupled AI Hosting Interface.
5. **Ingestion & Writing**: The returned analysis is parsed into `error_summary`, `root_cause`, and `remediation_suggestion`. The manager commits these fields back to the `ai_diagnostics` table and marks the status as `COMPLETED`.

---

## 3. Failsafe & Fault Isolation Design
To ensure that AI errors never interfere with the primary scheduling engine, the system enforces the following safety controls:

1. **Zero State Blocking**: An AI engine crash, request timeout, rate-limit rejection, or missing API key **must never** block or revert job state changes. The job remains in `FAILED` or `DLQ` state, and user-facing queueing continues unaffected.
2. **Timeout Boundaries**: All LLM host HTTP calls must enforce a strict connection and request timeout (Design Default: **5.0 seconds**). If the timeout is reached, the status is set to `FAILED` or `UNAVAILABLE` and execution terminates.
3. **Database Isolation**: Diagnostic data is stored in the separate `ai_diagnostics` table. This keeps the high-traffic `jobs` table query paths clean and isolates prompt metadata from operational tables.
4. **Fallback Output**: If the LLM call fails, the `DiagnosticStateManager` writes a predefined static template to the database, ensuring the user dashboard shows the raw logs with an advisory warning:
   - *Static Template Example*: `"AI Failure Diagnostics: Analysis Unavailable. Please inspect the raw logs below."`

---

## 4. Prompt Structure & Prompt Design
To ensure the LLM returns consistent, structured diagnostics that fit the PostgreSQL schemas, the prompt enforces strict output constraints.

### 4.1 System Prompt Template
```
You are an expert systems reliability engineer. Your job is to analyze the execution failure logs and metadata of a background worker task and output a highly structured, accurate root-cause analysis and remediation guide.

Your analysis must fit within three specific fields:
1. Error Summary: A concise, one-sentence description of the final error encountered (e.g. database timeout, connection error).
2. Root Cause: A detailed explanation of why the task failed, referencing line numbers, modules, or payload inputs from the log context.
3. Remediation Suggestion: Actionable steps a developer or operator can take to fix the error (e.g., config changes, code edits, credential checks).

Output Format Requirement:
You MUST respond strictly in the following JSON format. Do NOT include markdown blocks, backticks, or trailing prose:
{
  "error_summary": "Summary text here",
  "root_cause": "Detailed cause text here",
  "remediation_suggestion": "Actionable suggestion text here"
}
```

### 4.2 User Context Variable Injection
```
TASK HANDLER: {target_handler}
QUEUE NAME: {queue_name}
RETRY ATTEMPTS: {retries_total}
Sanitized Execution Logs (Truncated to 100 KB):
---
{sanitized_logs}
---
```

---

## 5. AI Model Hosting & Interface Decision
The AI Hosting Interface is decoupled via an HTTP client wrapper to keep the deployment footprint light:

- **Hosting Decision**: The MVP will utilize a **Local Open-Source LLM API Host (Ollama / vLLM)** or an **External API Gateway Wrapper** exposing a standard OpenAI-compatible `/v1/chat/completions` endpoint.
- **Client Strategy**:
  - The `AIDiagnosticsEngine` uses a standard async HTTP client (e.g., `httpx.AsyncClient`) to interact with the LLM API.
  - This avoids installing massive local deep learning libraries (like PyTorch, Transformers, or CUDA frameworks) inside the Control Plane or Execution Plane.
- **Configurability (Design Defaults)**:
  - Host URL: `http://localhost:11434` (Ollama local default).
  - Target Model: `llama3` or `mistral` (Design Default).
  - API Key: Loaded via environment variables (secret management deferred).

---

## 6. Mocking & Local Verification Strategy
To ensure unit test suites run fast and can execute in isolated environments (CI/CD pipelines) without calling live LLMs:

- **Mock Client**: A mock diagnostics client `MockAIDiagnosticsEngine` will be implemented under the testing module.
- **Mock Behavior**: When testing, if the environment flag `TESTING=true` is set, the LLM HTTP client calls are bypassed. Instead, the mock engine evaluates the `target_handler` name:
  - If `target_handler = 'tasks.simulate_db_timeout'`, it returns a predefined database timeout diagnostic response.
  - If `target_handler = 'tasks.simulate_network_split'`, it returns a network split diagnostic response.
  - If `target_handler = 'tasks.simulate_unhandled_exception'`, it returns a standard python syntax exception diagnostic response.
- This guarantees full code-coverage validation for the async state machine without network calls.
