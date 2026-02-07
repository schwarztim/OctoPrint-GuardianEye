"""
AI Vision Providers for GuardianEye.

Supports 6 providers, all using only the `requests` library:
  - OpenAI (gpt-4o-mini)
  - Azure OpenAI
  - Anthropic (claude-sonnet-4-20250514)
  - xAI / Grok (grok-2-vision-latest)
  - Google Gemini (gemini-2.0-flash)
  - Ollama (llava, fully local/free)

Ported from bambu-lab-mcp/src/vision-provider.ts with 3 new providers added.
"""

import time
import base64
import logging
import requests

_logger = logging.getLogger("octoprint.plugins.guardianeye.vision")

# Tiny 1x1 red JPEG for connection tests (156 bytes)
_TEST_IMAGE_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
    "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJ"
    "CQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf"
    "/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAA"
    "AAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAB//2Q=="
)


class VisionAnalysisResult:
    __slots__ = ("failed", "reason", "confidence", "provider", "model", "latency_ms", "cost")

    def __init__(self, failed, reason, confidence=0.0, provider="", model="", latency_ms=0, cost=0.0):
        self.failed = failed
        self.reason = reason
        self.confidence = confidence
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.cost = cost

    def to_dict(self):
        return {
            "failed": self.failed,
            "reason": self.reason,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "cost": self.cost,
        }


def _parse_verdict(reply):
    """Parse 'VERDICT: OK' or 'VERDICT: FAIL | reason' from AI response."""
    reply = reply.strip()
    upper = reply.upper()

    if "VERDICT: FAIL" in upper:
        idx = upper.index("VERDICT: FAIL")
        after = reply[idx + len("VERDICT: FAIL"):]
        reason = after.lstrip().lstrip("|").strip()
        return True, reason or "visual failure detected", 0.95

    if "VERDICT: OK" in upper:
        idx = upper.index("VERDICT: OK")
        after = reply[idx + len("VERDICT: OK"):]
        reason = after.lstrip().lstrip("|").strip()
        return False, reason or "print looks normal", 0.0

    # Fallback: if AI didn't follow format, be conservative (OK)
    _logger.warning("Vision response didn't match expected format, treating as OK: %s", reply[:200])
    return False, reply[:200], 0.0


class VisionProviderBase:
    name = "base"
    model = ""

    def analyze(self, image_base64, prompt):
        raise NotImplementedError

    def test_connection(self):
        """Send a minimal request to verify API credentials work."""
        try:
            result = self.analyze(_TEST_IMAGE_B64, "Respond with: VERDICT: OK")
            return True, f"Connected to {self.name}/{self.model} ({result.latency_ms}ms)"
        except Exception as e:
            return False, f"{self.name} error: {str(e)[:200]}"


class OpenAIVisionProvider(VisionProviderBase):
    name = "openai"

    def __init__(self, api_key, model="gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def analyze(self, image_base64, prompt):
        start = time.time()
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    ],
                }],
                "max_tokens": 150,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        failed, reason, confidence = _parse_verdict(reply)
        return VisionAnalysisResult(
            failed=failed, reason=reason, confidence=confidence,
            provider=self.name, model=self.model,
            latency_ms=int((time.time() - start) * 1000),
        )


class AzureOpenAIVisionProvider(VisionProviderBase):
    name = "azure_openai"

    def __init__(self, api_key, endpoint, deployment="gpt-4o-mini", api_version="2025-01-01-preview"):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.deployment = deployment
        self.model = deployment
        self.api_version = api_version

    def analyze(self, image_base64, prompt):
        start = time.time()
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "api-key": self.api_key},
            json={
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    ],
                }],
                "max_tokens": 150,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        failed, reason, confidence = _parse_verdict(reply)
        return VisionAnalysisResult(
            failed=failed, reason=reason, confidence=confidence,
            provider=self.name, model=self.model,
            latency_ms=int((time.time() - start) * 1000),
        )


class AnthropicVisionProvider(VisionProviderBase):
    name = "anthropic"

    def __init__(self, api_key, model="claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model

    def analyze(self, image_base64, prompt):
        start = time.time()
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "max_tokens": 150,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                reply = block.get("text", "").strip()
                break
        failed, reason, confidence = _parse_verdict(reply)
        return VisionAnalysisResult(
            failed=failed, reason=reason, confidence=confidence,
            provider=self.name, model=self.model,
            latency_ms=int((time.time() - start) * 1000),
        )


class XAIVisionProvider(VisionProviderBase):
    """xAI / Grok — uses OpenAI-compatible API format."""
    name = "xai"

    def __init__(self, api_key, model="grok-2-vision-latest"):
        self.api_key = api_key
        self.model = model

    def analyze(self, image_base64, prompt):
        start = time.time()
        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    ],
                }],
                "max_tokens": 150,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        failed, reason, confidence = _parse_verdict(reply)
        return VisionAnalysisResult(
            failed=failed, reason=reason, confidence=confidence,
            provider=self.name, model=self.model,
            latency_ms=int((time.time() - start) * 1000),
        )


class GeminiVisionProvider(VisionProviderBase):
    """Google Gemini — uses generativelanguage API with inline_data format."""
    name = "gemini"

    def __init__(self, api_key, model="gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model

    def analyze(self, image_base64, prompt):
        start = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            json={
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}},
                    ],
                }],
                "generationConfig": {"maxOutputTokens": 150},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    reply = part["text"].strip()
                    break
        failed, reason, confidence = _parse_verdict(reply)
        return VisionAnalysisResult(
            failed=failed, reason=reason, confidence=confidence,
            provider=self.name, model=self.model,
            latency_ms=int((time.time() - start) * 1000),
        )


class OllamaVisionProvider(VisionProviderBase):
    """Ollama — 100% local, free, no API key needed."""
    name = "ollama"

    def __init__(self, endpoint="http://localhost:11434", model="llava"):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    def analyze(self, image_base64, prompt):
        start = time.time()
        resp = requests.post(
            f"{self.endpoint}/api/chat",
            json={
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64],
                }],
                "stream": False,
                "options": {"num_predict": 150},
            },
            timeout=120,  # Local models can be slow
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("message", {}).get("content", "").strip()
        failed, reason, confidence = _parse_verdict(reply)
        return VisionAnalysisResult(
            failed=failed, reason=reason, confidence=confidence,
            provider=self.name, model=self.model,
            latency_ms=int((time.time() - start) * 1000),
            cost=0.0,  # Always free
        )

    def test_connection(self):
        """Check if Ollama is running and the model is available."""
        try:
            resp = requests.get(f"{self.endpoint}/api/tags", timeout=10)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            # Ollama model names may include :latest suffix
            found = any(self.model in m for m in models)
            if found:
                return True, f"Ollama running, model '{self.model}' available"
            return False, f"Ollama running but model '{self.model}' not found. Available: {', '.join(models[:5])}"
        except requests.ConnectionError:
            return False, f"Cannot connect to Ollama at {self.endpoint}. Is it running?"
        except Exception as e:
            return False, f"Ollama error: {str(e)[:200]}"


def create_vision_provider(settings):
    """Factory: create a provider from OctoPrint plugin settings dict."""
    provider_name = settings.get("provider", "openai")
    api_key = settings.get("api_key", "")

    if provider_name == "openai":
        return OpenAIVisionProvider(api_key, model=settings.get("openai_model", "gpt-4o-mini"))

    elif provider_name == "azure_openai":
        return AzureOpenAIVisionProvider(
            api_key=api_key,
            endpoint=settings.get("azure_endpoint", ""),
            deployment=settings.get("azure_deployment", "gpt-4o-mini"),
            api_version=settings.get("azure_api_version", "2025-01-01-preview"),
        )

    elif provider_name == "anthropic":
        return AnthropicVisionProvider(api_key, model=settings.get("anthropic_model", "claude-sonnet-4-20250514"))

    elif provider_name == "xai":
        return XAIVisionProvider(api_key, model=settings.get("xai_model", "grok-2-vision-latest"))

    elif provider_name == "gemini":
        return GeminiVisionProvider(api_key, model=settings.get("gemini_model", "gemini-2.0-flash"))

    elif provider_name == "ollama":
        return OllamaVisionProvider(
            endpoint=settings.get("ollama_endpoint", "http://localhost:11434"),
            model=settings.get("ollama_model", "llava"),
        )

    else:
        raise ValueError(f"Unknown vision provider: {provider_name}")
