"""LLM API client for OpenAI-compatible APIs (including vLLM)."""

import time
import random
from typing import Tuple, Optional, List
import concurrent.futures

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class LLMClient:
    """
    Unified LLM API client supporting vLLM and OpenAI-compatible APIs.
    """

    def __init__(self, api_base: str, model_name: str, api_key: str = "EMPTY", timeout: Optional[int] = None):
        """
        Initialize LLM client.

        Args:
            api_base: API base URL, e.g., "http://localhost:8000/v1"
            model_name: Model name.
            api_key: API key (default "EMPTY" for local vLLM).
            timeout: Request timeout in seconds (None = no timeout).
        """
        if OpenAI is None:
            raise ImportError("openai package is required. Install with: pip install openai")

        self.api_base = api_base
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        max_retries: int = 10
    ) -> Tuple[Optional[str], bool]:
        """
        Call LLM for inference.

        Args:
            prompt: Input prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum generation token count.
            top_p: Top-p sampling parameter.
            max_retries: Maximum number of retries.

        Returns:
            (response_text, api_failed)
            - response_text: Generated text, or None on failure.
            - api_failed: Whether the API call failed.
        """
        client = OpenAI(base_url=self.api_base, api_key=self.api_key, timeout=self.timeout)

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful SQL expert."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                )
                return response.choices[0].message.content, False

            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"[ERROR] API Error (Attempt {attempt+1}/{max_retries}): {e}")
                    return None, True

                # Exponential backoff with jitter
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"[WARNING] API Error (Attempt {attempt+1}/{max_retries}), retrying in {wait_time:.2f}s... Error: {e}")
                time.sleep(wait_time)

        return None, True

    def generate_batch(
        self,
        prompts: List[str],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        num_workers: int = 4,
        show_progress: bool = True,
        max_retries: int = 10,
        on_result: callable = None
    ) -> List[Optional[str]]:
        """
        Batch LLM inference using thread pool concurrency.

        Args:
            prompts: List of prompts.
            temperature: Sampling temperature.
            max_tokens: Maximum generation token count.
            top_p: Top-p sampling parameter.
            num_workers: Number of worker threads (default 4).
            show_progress: Whether to show progress bar.
            max_retries: Maximum number of retries.
            on_result: Optional callback, signature on_result(index, response).

        Returns:
            List of generated texts (in same order as prompts).
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(
                    self._generate_single,
                    prompt,
                    self.api_base,
                    self.model_name,
                    self.api_key,
                    self.timeout,
                    temperature,
                    max_tokens,
                    top_p,
                    max_retries
                )
                for prompt in prompts
            ]

            iterator = concurrent.futures.as_completed(futures)
            if show_progress and tqdm is not None:
                iterator = tqdm(iterator, total=len(prompts), desc="LLM Inference")

            # Collect results in original order
            future_to_idx = {f: i for i, f in enumerate(futures)}
            ordered_results = [None] * len(prompts)

            for future in iterator:
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    ordered_results[idx] = result
                    if on_result is not None:
                        on_result(idx, result)
                except Exception as e:
                    print(f"[ERROR] Batch inference error for prompt {idx}: {e}")
                    ordered_results[idx] = None
                    if on_result is not None:
                        on_result(idx, None)

        return ordered_results

    @staticmethod
    def _generate_single(
        prompt: str,
        api_base: str,
        model_name: str,
        api_key: str,
        timeout: Optional[int],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        max_retries: int = 10
    ) -> Optional[str]:
        """
        Single prompt inference (static method for thread pool).

        Args:
            prompt: Input prompt.
            api_base: API base URL.
            model_name: Model name.
            api_key: API key.
            timeout: Request timeout.
            temperature: Sampling temperature.
            max_tokens: Maximum generation token count.
            top_p: Top-p sampling parameter.
            max_retries: Maximum number of retries.

        Returns:
            Generated text, or None on failure.
        """
        client = OpenAI(base_url=api_base, api_key=api_key, timeout=timeout)

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful SQL generation assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                )
                return response.choices[0].message.content

            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"[ERROR] API Error (Attempt {attempt+1}/{max_retries}): {e}")
                    return None

                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"[WARNING] API Error (Attempt {attempt+1}/{max_retries}), retrying in {wait_time:.2f}s... Error: {e}")
                time.sleep(wait_time)

        return None
