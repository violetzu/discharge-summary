"""
vLLM OpenAI-compatible client
  Streaming : POST /v1/completions  (SSE)
  Completion: POST /v1/completions  (non-stream)
"""
import json
from typing import AsyncGenerator
import aiohttp
from .config import settings


async def generate_stream(model: str, prompt: str, base_url: str) -> AsyncGenerator[str, None]:
    url = f"{base_url}/v1/completions"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "max_tokens": 2048,
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 64,
        "repetition_penalty": 1.001,
        "stop": ["<end_of_turn>", "<eos>"],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                error = await resp.text()
                yield json.dumps({"text": "", "done": True, "error": error})
                return
            async for raw in resp.content:
                line = raw.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]  # strip "data: "
                if data == "[DONE]":
                    yield json.dumps({"text": "", "done": True})
                    return
                try:
                    chunk = json.loads(data)
                    text = chunk["choices"][0].get("text", "")
                    finish = chunk["choices"][0].get("finish_reason")
                    yield json.dumps({"text": text, "done": finish is not None})
                except Exception:
                    continue


async def generate_completion(model: str, prompt: str, base_url: str) -> str:
    url = f"{base_url}/v1/completions"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "max_tokens": 1024,
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 64,
        "repetition_penalty": 1.001,
        "stop": ["<end_of_turn>", "<eos>"],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["choices"][0]["text"]
