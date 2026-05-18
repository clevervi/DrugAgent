import os
import requests
from typing import Optional


def _read_timeout_sec() -> float:
    try:
        return float(os.environ.get("LOCAL_LLM_TIMEOUT", "300"))
    except ValueError:
        return 300.0


def _connect_timeout_sec() -> float:
    try:
        return float(os.environ.get("LOCAL_LLM_CONNECT_TIMEOUT", "15"))
    except ValueError:
        return 15.0


class LocalChatModel:
    """Clase compatible con LangChain para interactuar con LLMs locales (Ollama/LM Studio)."""
    def __init__(self, model_name: str = None, base_url: str = None, temperature: float = 0.1):
        self.model_name = model_name or os.environ.get("LOCAL_LLM_MODEL", "qwen2.5-coder:7b")
        self.base_url = base_url or os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        self.temperature = temperature

    def invoke(self, messages):
        formatted_messages = []
        if isinstance(messages, str):
            formatted_messages.append({"role": "user", "content": messages})
        else:
            for msg in messages:
                role = "user"
                if hasattr(msg, "__class__") and msg.__class__.__name__ == "SystemMessage":
                    role = "system"
                elif hasattr(msg, "__class__") and msg.__class__.__name__ == "AIMessage":
                    role = "assistant"
                elif isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    formatted_messages.append({"role": role, "content": content})
                    continue

                formatted_messages.append({"role": role, "content": msg.content})

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": self.temperature,
        }
        json_mode = os.environ.get("LOCAL_LLM_JSON_MODE", "true").lower() in ("1", "true", "yes")
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        read_t = _read_timeout_sec()
        conn_t = _connect_timeout_sec()
        timeout = (conn_t, read_t)

        try:
            print(f"   [LLM Local] Consultando ({self.model_name}) en {url} (timeout lectura={read_t:.0f}s)...")
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)

            if response.status_code == 400 and json_mode:
                print("   [LLM Local] Advertencia: servidor rechazó 'response_format'. Reintentando sin JSON mode...")
                payload.pop("response_format", None)
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)

            response.raise_for_status()
            body = response.json()
            content = _extract_message_content(body)
            if content is None:
                raise ValueError(f"Respuesta sin contenido usable: claves={list(body.keys())[:12]}")

            class MockResponse:
                def __init__(self, content):
                    self.content = content

            return MockResponse(content)
        except Exception as e:
            print(f"   [LLM Local] Error en LLM Local: {e}")
            raise e


def _extract_message_content(body: dict) -> Optional[str]:
    """OpenAI-compatible (choices[0].message.content) y fallbacks Ollama/otros."""
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            if isinstance(first.get("text"), str):
                return first["text"]
    msg = body.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        return msg["content"]
    if isinstance(body.get("response"), str):
        return body["response"]
    return None
