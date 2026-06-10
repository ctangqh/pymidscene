"""
使用 OpenAI SDK + DeepSeek 兼容端点测试“视觉模型”是否可用。

默认使用：
- base_url: https://api.deepseek.com/v1
- model: deepseek-v4-pro

示例（PowerShell）：
  $env:DEEPSEEK_API_KEY="..."
  python examples/deepseek_vision_test.py --image output/ui_debug/notepad_close_state_step1_raw.png --prompt "请描述这张图片"
"""
import argparse
import base64
import os
import sys
from pathlib import Path

from openai import OpenAI
from openai import BadRequestError
from openai import NotFoundError

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from common.config import settings


def _guess_mime(image_path: Path) -> str:
    ext = image_path.suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext in ("webp",):
        return "image/webp"
    if ext in ("gif",):
        return "image/gif"
    return "image/png"


def _normalize_base_url(url: str) -> str:
    url = (url or "").strip()
    url = url.strip("`").strip().strip('"').strip("'")
    return url.rstrip("/")


def _build_markdown_payload(prompt: str, mime: str, image_b64: str) -> str:
    return f"{prompt}\n\n![image](data:{mime};base64,{image_b64})"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="本地图片路径（png/jpg/webp/gif）")
    parser.add_argument("--prompt", default="请描述这张图片的内容。", help="文本问题")
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or settings.vision_config.model or "deepseek-v4-pro")
    parser.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL") or settings.vision_config.base_url or "https://api.deepseek.com/v1")
    parser.add_argument("--api-key", default=os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY") or settings.vision_config.api_key)
    args = parser.parse_args()

    if not args.api_key:
        raise RuntimeError("Missing api key. Set DEEPSEEK_API_KEY (or LLM_API_KEY).")

    image_path = Path(args.image)
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    mime = _guess_mime(image_path)
    image_data_url = f"data:{mime};base64,{image_b64}"
    markdown_payload = _build_markdown_payload(args.prompt, mime, image_b64)

    provided_base = _normalize_base_url(args.base_url)
    candidates = [
        provided_base,
        "https://api.deepseek.com/v1",
        "https://api.deepseek.com/v1/compat",
        "https://api.deepseek.com",
    ]
    seen = set()
    base_urls = []
    for item in candidates:
        item = _normalize_base_url(item)
        if not item or item in seen:
            continue
        seen.add(item)
        base_urls.append(item)

    last_nf: Exception | None = None
    last_br: Exception | None = None
    for base_url in base_urls:
        try:
            client = OpenAI(api_key=args.api_key, base_url=base_url)
            try:
                resp = client.chat.completions.create(
                    model=args.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": image_data_url}},
                                {"type": "text", "text": args.prompt},
                            ],
                        }
                    ],
                    temperature=0.1,
                    max_tokens=512,
                )
                print(f"[base_url={base_url} format=image_url]")
                print(resp.choices[0].message.content)
                return
            except BadRequestError as e:
                last_br = e
                message = str(e)
                if "unknown variant `image_url`" not in message:
                    raise
                try:
                    resp = client.chat.completions.create(
                        model=args.model,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image", "image": {"data": image_b64, "format": "base64"}},
                                    {"type": "text", "text": args.prompt},
                                ],
                            }
                        ],
                        temperature=0.1,
                        max_tokens=512,
                    )
                    print(f"[base_url={base_url} format=image(base64)]")
                    print(resp.choices[0].message.content)
                    return
                except BadRequestError as e2:
                    last_br = e2
                    message2 = str(e2)
                    if "unknown variant `image`" not in message2:
                        raise
                    resp = client.chat.completions.create(
                        model=args.model,
                        messages=[{"role": "user", "content": markdown_payload}],
                        temperature=0.1,
                        max_tokens=512,
                    )
                    print(f"[base_url={base_url} format=markdown_data_url]")
                    print(resp.choices[0].message.content)
                    return
        except NotFoundError as e:
            last_nf = e
            continue

    if last_nf is not None and last_br is None:
        raise RuntimeError(f"All base_url candidates returned 404 Not Found: {base_urls}") from last_nf
    raise RuntimeError(f"All base_url candidates failed: {base_urls}") from (last_br or last_nf)


if __name__ == "__main__":
    main()
