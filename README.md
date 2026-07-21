# vLLM Priority Scheduling Test

This repository contains a test script to verify that priority scheduling works correctly in a vLLM deployment.

## Overview

The test script sends requests with different priority levels to a vLLM server and verifies that they are processed in the correct order.

**Important:** In vLLM, LOWER priority values are processed FIRST (opposite of typical priority systems).

- **Negative priority** (-50) - should complete FIRST (highest priority)
- **Zero priority** (explicit 0) - should complete second (medium priority)
- **Default priority** (no priority specified) - should behave like priority 0
- **High priority** (100) - should complete LAST (lowest priority)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

After deploying your model to OpenShift using `llm-infra.yaml`, run the test:

```bash
# With API key as argument
python test_priority_scheduling.py \
  --url https://<your-model-endpoint> \
  --model gpt-oss-20b \
  --api-key your-api-key-here

# Or using environment variable
export OPENAI_API_KEY=your-api-key-here
python test_priority_scheduling.py --url https://<your-model-endpoint>
```

If your deployment doesn't require authentication (as indicated by `security.opendatahub.io/enable-auth: 'false'` in your YAML), you can omit the `--api-key` parameter.

**Using the Messages API** (instead of Completions API):

```bash
python test_priority_scheduling.py \
  --url https://<your-model-endpoint> \
  --api-format messages
```

### Command Line Options

```bash
python test_priority_scheduling.py \
  --url https://localhost:8000 \
  --model gpt-oss-20b \
  --requests-per-priority 4 \
  --prompt-tokens 1500 \
  --max-tokens 500 \
  --negative-priority -50 \
  --low-priority 0 \
  --high-priority 100
```

**Options:**
- `--url`: Base URL of the vLLM server (default: `https://localhost:8000`)
- `--model`: Model name (default: `gpt-oss-20b`)
- `--api-key`: API key for authentication (optional, can also use `OPENAI_API_KEY` env var)
- `--api-format`: API format - `completions` for `/v1/completions` or `messages` for `/v1/messages` (default: `completions`)
- `--requests-per-priority`: Number of requests to send for each priority tier (default: 4)
- `--prompt-tokens`: Approximate number of tokens in the prompt (default: 1500)
- `--max-tokens`: Maximum tokens to generate per request (default: 500)
- `--negative-priority`: Priority value for negative priority requests (default: -50)
- `--low-priority`: Priority value for low priority requests (default: 0)
- `--high-priority`: Priority value for high priority requests (default: 100)

## How It Works

1. **Sends all requests simultaneously**: All requests are sent at exactly the same time with identical prompts and identical `max_tokens`. The **only** variable is the priority value. This ensures the test measures pure priority scheduling, not submission order or prompt length effects.

2. **Uses large prompts to saturate the server**: By default, each request uses ~1500 tokens of prompt and requests 500 tokens of generation. With 16 requests (4 per priority tier) on a single GPU, this creates real queueing and allows priority to make a difference.

3. **Monitors completion order**: Each request is timestamped when sent and when completed.

4. **Verifies priority ordering**: The script checks (lower values = higher priority):
   - ✓ Negative priority completes before zero priority
   - ✓ Negative priority completes before default priority
   - ✓ Negative priority completes before high value priority (100)
   - ✓ Zero/default priority completes before high value priority (100)
   - ✓ Default priority behaves like explicit priority 0

5. **Outputs results**: The script prints:
   - Completion order with timestamps
   - Verification checks with pass/fail status
   - Overall test result
   - Saves detailed results to `priority_test_results.json`

## Expected Output

```
================================================================================
PRIORITY SCHEDULING TEST
================================================================================
Sending 16 requests SIMULTANEOUSLY:
  - 4 with priority -50 (highest)
  - 4 with priority 0
  - 4 with default priority (no priority specified)
  - 4 with priority 100 (lowest)
All requests use identical prompts (~1500 tokens) and max_tokens=500
Expected: LOWER priority values complete first.

[timestamp] Creating all requests...
[timestamp] Sending all 16 requests NOW...

[timestamp] Sending request NEG-1 with priority -50
[timestamp] Sending request NEG-2 with priority -50
[timestamp] Sending request ZERO-1 with priority 0
...
[timestamp] ✓ Request NEG-1 completed in 3.45s
[timestamp] ✓ Request NEG-2 completed in 3.67s
...

================================================================================
RESULTS ANALYSIS
================================================================================

Completion order:
1. ✓ NEG-1 (priority: -50) - 1.23s
2. ✓ NEG-2 (priority: -50) - 1.45s
3. ✓ DEFAULT-1 (priority: default) - 2.10s
4. ✓ DEFAULT-2 (priority: default) - 2.25s
5. ✓ ZERO-1 (priority: 0) - 2.30s
6. ✓ ZERO-2 (priority: 0) - 2.50s
7. ✓ HIGH-1 (priority: 100) - 3.40s
8. ✓ HIGH-2 (priority: 100) - 3.55s

--------------------------------------------------------------------------------
PRIORITY SCHEDULING VERIFICATION
(In vLLM: LOWER priority values are processed FIRST)
--------------------------------------------------------------------------------

✓ Check 1: Negative priority (highest) before zero priority
✓ Check 2: Negative priority before default priority
✓ Check 3: Negative priority before high value priority (100)
✓ Check 4: Zero/default priority before high value priority (100)
✓ Check 5: Default priority behaves like priority 0

--------------------------------------------------------------------------------
✓ ALL CHECKS PASSED - PRIORITY SCHEDULING WORKS CORRECTLY!
--------------------------------------------------------------------------------
```

## How Priority is Sent

This test script sends the `priority` parameter as a **top-level field** in the JSON request body when making raw HTTP requests:

```json
{
  "model": "gpt-oss-20b",
  "prompt": "...",
  "max_tokens": 500,
  "temperature": 0.7,
  "priority": -50
}
```

**Note:** If you're using the OpenAI Python client SDK instead of raw HTTP requests, you need to pass priority via `extra_body`:

```python
from openai import OpenAI

client = OpenAI(base_url="https://your-endpoint", api_key="...")
completion = client.chat.completions.create(
    model="gpt-oss-20b",
    messages=[{"role": "user", "content": "Prompt"}],
    extra_body={"priority": 10}  # Lower values = higher priority
)
```

In vLLM, **lower priority values are processed first**. Default priority is 0.

**References:**
- [vLLM Priority Scheduling RFC](https://github.com/vllm-project/vllm/issues/6077)
- [vLLM OpenAI-Compatible Server Docs](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/)

## Deployment Configuration

The `llm-infra.yaml` file configures vLLM with priority scheduling enabled via:

```yaml
env:
  - name: VLLM_ADDITIONAL_ARGS
    value: "--disable-uvicorn-access-log --max-model-len=2000 --gpu-memory-utilization=0.8 --scheduling-policy priority"
```

Note: There's a typo in the original config (`--scheduling-policy¶ priority`). Make sure to fix this to `--scheduling-policy priority` before deploying.

## Troubleshooting

### SSL Certificate Errors
The test script disables SSL verification by default (`verify=False`). For production, update the code to use proper certificates.

### Connection Refused
Make sure the vLLM server is running and accessible at the specified URL. Check your OpenShift route/service configuration.

### Priority Not Working
If the test fails, verify:
1. The `--scheduling-policy priority` flag is correctly set in your deployment
2. There's no typo in the VLLM_ADDITIONAL_ARGS
3. The vLLM version supports priority scheduling
4. Check vLLM server logs for any errors

## License

MIT