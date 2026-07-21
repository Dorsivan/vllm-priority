#!/usr/bin/env python3
"""
Test script for vLLM priority scheduling.

This script sends multiple requests with different priorities to a vLLM server
and verifies that higher priority requests are processed before lower priority ones.
"""

import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any
import httpx
import json


class PriorityTest:
    def __init__(self, base_url: str, model_name: str = "gpt-oss-20b", api_key: str = None, api_format: str = "completions"):
        """
        Initialize the priority test.

        Args:
            base_url: Base URL of the vLLM server (e.g., "https://localhost:8000")
            model_name: Name of the model being served
            api_key: API key for authentication (optional)
            api_format: API format to use - "completions" or "messages" (default: "completions")
        """
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.api_key = api_key
        self.api_format = api_format
        self.results: List[Dict[str, Any]] = []

    async def send_request(
        self,
        prompt: str,
        priority: int | None,
        request_id: str,
        max_tokens: int = 100
    ) -> Dict[str, Any]:
        """
        Send a request with specified priority.

        Args:
            prompt: The prompt text
            priority: Priority value (lower = higher priority), or None to omit
            request_id: Unique identifier for this request
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary with request details and timing
        """
        # Build URL and payload based on API format
        if self.api_format == "messages":
            url = f"{self.base_url}/v1/messages"
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }
        else:  # completions
            url = f"{self.base_url}/v1/completions"
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }

        if priority is not None:
            payload["priority"] = priority

        start_time = time.time()
        send_timestamp = datetime.now().isoformat()

        print(f"[{send_timestamp}] Sending request {request_id} with priority {priority} (API: {self.api_format})")

        # Prepare headers
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Messages API uses anthropic-version header
        if self.api_format == "messages":
            headers["anthropic-version"] = "2023-06-01"

        async with httpx.AsyncClient(verify=False, timeout=300.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                end_time = time.time()
                complete_timestamp = datetime.now().isoformat()
                duration = end_time - start_time

                result = {
                    "request_id": request_id,
                    "priority": priority,
                    "sent_at": send_timestamp,
                    "completed_at": complete_timestamp,
                    "duration_seconds": duration,
                    "status": "success",
                    "response": response.json()
                }

                print(f"[{complete_timestamp}] ✓ Request {request_id} completed in {duration:.2f}s")

                return result

            except Exception as e:
                end_time = time.time()
                error_timestamp = datetime.now().isoformat()
                duration = end_time - start_time

                result = {
                    "request_id": request_id,
                    "priority": priority,
                    "sent_at": send_timestamp,
                    "completed_at": error_timestamp,
                    "duration_seconds": duration,
                    "status": "error",
                    "error": str(e)
                }

                print(f"[{error_timestamp}] ✗ Request {request_id} failed: {e}")

                return result

    async def run_concurrent_test(
        self,
        requests_per_priority: int = 4,
        negative_priority_value: int = -50,
        low_priority_value: int = 0,
        high_priority_value: int = 100,
        prompt_tokens: int = 1500,
        max_tokens: int = 5000
    ):
        """
        Run a test where identical requests with different priorities are sent simultaneously.

        In vLLM, LOWER priority values are processed FIRST.

        Args:
            requests_per_priority: Number of requests to send for each priority tier
            negative_priority_value: Priority value for negative priority requests
            low_priority_value: Priority value for low priority requests
            high_priority_value: Priority value for high priority requests
            prompt_tokens: Approximate number of tokens in the prompt (controls load)
            max_tokens: Maximum tokens to generate per request
        """
        print("\n" + "="*80)
        print("PRIORITY SCHEDULING TEST")
        print("="*80)
        print(f"Sending {requests_per_priority * 4} requests SIMULTANEOUSLY:")
        print(f"  - {requests_per_priority} with priority {negative_priority_value} (highest)")
        print(f"  - {requests_per_priority} with priority {low_priority_value}")
        print(f"  - {requests_per_priority} with default priority (no priority specified)")
        print(f"  - {requests_per_priority} with priority {high_priority_value} (lowest)")
        print(f"All requests use identical prompts (~{prompt_tokens} tokens) and max_tokens={max_tokens}")
        print("Expected: LOWER priority values complete first.\n")

        # Create a large, consistent prompt to saturate the server
        # Repeat a paragraph to reach approximately the target token count
        # Very rough estimate: ~4 characters per token
        base_text = (
            "In the vast expanse of the cosmos, humanity has always looked to the stars "
            "with wonder and curiosity. From ancient civilizations mapping constellations "
            "to modern space exploration, our journey into the unknown continues to push "
            "the boundaries of what is possible. The development of advanced technologies "
            "has enabled us to send probes to distant planets, establish orbital stations, "
            "and dream of interstellar travel. "
        )

        # Repeat to reach target length
        chars_per_token = 4  # rough estimate
        target_chars = prompt_tokens * chars_per_token
        repetitions = max(1, target_chars // len(base_text))
        large_prompt = base_text * repetitions

        all_tasks = []

        # Create all requests with the SAME prompt and max_tokens, varying only priority
        print(f"[{datetime.now().isoformat()}] Scheduling all requests to start simultaneously...")

        # Negative priority (highest priority - should complete first)
        for i in range(requests_per_priority):
            task = asyncio.create_task(self.send_request(
                prompt=large_prompt,
                priority=negative_priority_value,
                request_id=f"NEG-{i+1}",
                max_tokens=max_tokens
            ))
            all_tasks.append(task)

        # Zero priority
        for i in range(requests_per_priority):
            task = asyncio.create_task(self.send_request(
                prompt=large_prompt,
                priority=low_priority_value,
                request_id=f"ZERO-{i+1}",
                max_tokens=max_tokens
            ))
            all_tasks.append(task)

        # Default priority (no priority specified)
        for i in range(requests_per_priority):
            task = asyncio.create_task(self.send_request(
                prompt=large_prompt,
                priority=None,
                request_id=f"DEFAULT-{i+1}",
                max_tokens=max_tokens
            ))
            all_tasks.append(task)

        # High priority value (lowest priority - should complete last)
        for i in range(requests_per_priority):
            task = asyncio.create_task(self.send_request(
                prompt=large_prompt,
                priority=high_priority_value,
                request_id=f"HIGH-{i+1}",
                max_tokens=max_tokens
            ))
            all_tasks.append(task)

        # All tasks are now running in the background - wait for them to complete
        print(f"[{datetime.now().isoformat()}] All {len(all_tasks)} requests are now sending...\n")
        self.results = await asyncio.gather(*all_tasks)

        # Analyze results
        self.analyze_results()

    def analyze_results(self):
        """Analyze the results and verify priority scheduling worked correctly."""
        print("\n" + "="*80)
        print("RESULTS ANALYSIS")
        print("="*80)

        # Sort by completion time
        sorted_results = sorted(self.results, key=lambda x: x['completed_at'])

        print("\nCompletion order:")
        for i, result in enumerate(sorted_results, 1):
            status_icon = "✓" if result['status'] == 'success' else "✗"
            priority_str = str(result['priority']) if result['priority'] is not None else "default"
            print(f"{i}. {status_icon} {result['request_id']} (priority: {priority_str}) - "
                  f"{result['duration_seconds']:.2f}s")

        # Group results by priority type
        high_priority_results = [r for r in self.results if r['request_id'].startswith('HIGH')]  # priority 100 - lowest priority
        zero_priority_results = [r for r in self.results if r['request_id'].startswith('ZERO')]  # priority 0 - medium priority
        default_priority_results = [r for r in self.results if r['request_id'].startswith('DEFAULT')]  # no priority - likely 0
        negative_priority_results = [r for r in self.results if r['request_id'].startswith('NEG')]  # negative - highest priority

        print("\n" + "-"*80)
        print("PRIORITY SCHEDULING VERIFICATION")
        print("(In vLLM: LOWER priority values are processed FIRST)")
        print("-"*80)

        all_checks_pass = True

        # Check 1: Negative priority (highest) completes before zero priority
        if negative_priority_results and zero_priority_results:
            latest_neg = max(r['completed_at'] for r in negative_priority_results)
            earliest_zero = min(r['completed_at'] for r in zero_priority_results)

            neg_before_zero = latest_neg < earliest_zero
            check_icon = "✓" if neg_before_zero else "✗"
            print(f"\n{check_icon} Check 1: Negative priority (highest) before zero priority")
            print(f"    Latest NEGATIVE completion: {latest_neg}")
            print(f"    Earliest ZERO completion: {earliest_zero}")
            all_checks_pass = all_checks_pass and neg_before_zero

        # Check 2: Negative priority completes before default priority
        if negative_priority_results and default_priority_results:
            latest_neg = max(r['completed_at'] for r in negative_priority_results)
            earliest_default = min(r['completed_at'] for r in default_priority_results)

            neg_before_default = latest_neg < earliest_default
            check_icon = "✓" if neg_before_default else "✗"
            print(f"\n{check_icon} Check 2: Negative priority before default priority")
            print(f"    Latest NEGATIVE completion: {latest_neg}")
            print(f"    Earliest DEFAULT completion: {earliest_default}")
            all_checks_pass = all_checks_pass and neg_before_default

        # Check 3: Negative priority completes before high priority (100)
        if negative_priority_results and high_priority_results:
            latest_neg = max(r['completed_at'] for r in negative_priority_results)
            earliest_high = min(r['completed_at'] for r in high_priority_results)

            neg_before_high = latest_neg < earliest_high
            check_icon = "✓" if neg_before_high else "✗"
            print(f"\n{check_icon} Check 3: Negative priority before high value priority (100)")
            print(f"    Latest NEGATIVE completion: {latest_neg}")
            print(f"    Earliest HIGH (100) completion: {earliest_high}")
            all_checks_pass = all_checks_pass and neg_before_high

        # Check 4: Zero/default priority completes before high priority (100)
        zero_or_default_results = zero_priority_results + default_priority_results
        if zero_or_default_results and high_priority_results:
            latest_zero = max(r['completed_at'] for r in zero_or_default_results)
            earliest_high = min(r['completed_at'] for r in high_priority_results)

            zero_before_high = latest_zero < earliest_high
            check_icon = "✓" if zero_before_high else "✗"
            print(f"\n{check_icon} Check 4: Zero/default priority before high value priority (100)")
            print(f"    Latest ZERO/DEFAULT completion: {latest_zero}")
            print(f"    Earliest HIGH (100) completion: {earliest_high}")
            all_checks_pass = all_checks_pass and zero_before_high

        # Check 5: Verify default and explicit 0 priority behave the same
        if default_priority_results and zero_priority_results:
            # Get average completion times
            default_times = [r['completed_at'] for r in default_priority_results]
            zero_times = [r['completed_at'] for r in zero_priority_results]

            # Check if they're interleaved (which would suggest same priority)
            default_avg_index = sum(sorted_results.index(r) for r in default_priority_results) / len(default_priority_results)
            zero_avg_index = sum(sorted_results.index(r) for r in zero_priority_results) / len(zero_priority_results)

            similar_position = abs(default_avg_index - zero_avg_index) < 2
            check_icon = "✓" if similar_position else "~"
            print(f"\n{check_icon} Check 5: Default priority behaves like priority 0")
            print(f"    Avg position of DEFAULT: {default_avg_index:.1f}")
            print(f"    Avg position of ZERO: {zero_avg_index:.1f}")
            print(f"    (Similar positions suggest default=0)")

        print("\n" + "-"*80)
        if all_checks_pass:
            print("✓ ALL CHECKS PASSED - PRIORITY SCHEDULING WORKS CORRECTLY!")
        else:
            print("✗ SOME CHECKS FAILED - PRIORITY SCHEDULING MAY NOT BE WORKING!")
        print("-"*80)

        return all_checks_pass

    def save_results(self, filename: str = "priority_test_results.json"):
        """Save test results to a JSON file."""
        with open(filename, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'results': self.results
            }, f, indent=2)
        print(f"\n✓ Results saved to {filename}")


async def main():
    """Main function to run the priority test."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description='Test vLLM priority scheduling')
    parser.add_argument(
        '--url',
        default='https://localhost:8000',
        help='Base URL of the vLLM server (default: https://localhost:8000)'
    )
    parser.add_argument(
        '--model',
        default='gpt-oss-20b',
        help='Model name (default: gpt-oss-20b)'
    )
    parser.add_argument(
        '--api-key',
        default=None,
        help='API key for authentication (optional, can also use OPENAI_API_KEY env var)'
    )
    parser.add_argument(
        '--api-format',
        choices=['completions', 'messages'],
        default='completions',
        help='API format to use: "completions" for /v1/completions or "messages" for /v1/messages (default: completions)'
    )
    parser.add_argument(
        '--requests-per-priority',
        type=int,
        default=4,
        help='Number of requests to send for each priority tier (default: 4)'
    )
    parser.add_argument(
        '--prompt-tokens',
        type=int,
        default=1500,
        help='Approximate number of tokens in the prompt (default: 1500)'
    )
    parser.add_argument(
        '--max-tokens',
        type=int,
        default=500,
        help='Maximum tokens to generate per request (default: 500)'
    )
    parser.add_argument(
        '--negative-priority',
        type=int,
        default=-50,
        help='Priority value for negative priority requests (default: -50)'
    )
    parser.add_argument(
        '--low-priority',
        type=int,
        default=0,
        help='Priority value for low priority requests (default: 0)'
    )
    parser.add_argument(
        '--high-priority',
        type=int,
        default=100,
        help='Priority value for high priority requests (default: 100)'
    )

    args = parser.parse_args()

    # Get API key from args or environment variable
    api_key = args.api_key or os.getenv('OPENAI_API_KEY')

    tester = PriorityTest(
        base_url=args.url,
        model_name=args.model,
        api_key=api_key,
        api_format=args.api_format
    )

    await tester.run_concurrent_test(
        requests_per_priority=args.requests_per_priority,
        negative_priority_value=args.negative_priority,
        low_priority_value=args.low_priority,
        high_priority_value=args.high_priority,
        prompt_tokens=args.prompt_tokens,
        max_tokens=args.max_tokens
    )

    tester.save_results()


if __name__ == "__main__":
    asyncio.run(main())
