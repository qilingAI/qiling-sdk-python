"""Official OpenAI SDK example; set QILING_API_KEY, QILING_BASE_URL and QILING_MODEL."""
from __future__ import annotations

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="使用官方 OpenAI SDK 调用器灵文本模型（消耗调用余额）。")
    parser.add_argument("--prompt", required=True, help="发送给所选模型的文本。")
    parser.add_argument("--stream", action="store_true", help="使用官方 SSE 流式调用。")
    args = parser.parse_args()
    missing = [name for name in ("QILING_API_KEY", "QILING_BASE_URL", "QILING_MODEL") if not os.environ.get(name)]
    if missing:
        parser.error("请设置 " + ", ".join(missing) + "；Base URL 须包含 /v1。")
    from openai import OpenAI

    with OpenAI(api_key=os.environ["QILING_API_KEY"], base_url=os.environ["QILING_BASE_URL"], max_retries=0) as client:
        result = client.chat.completions.create(
            model=os.environ["QILING_MODEL"],
            messages=[{"role": "user", "content": args.prompt}],
            stream=args.stream,
        )
        if not args.stream:
            print(result.choices[0].message.content)
            return
        try:
            for chunk in result:
                if chunk.choices:
                    print(chunk.choices[0].delta.content or "", end="", flush=True)
            print()
        finally:
            result.close()


if __name__ == "__main__":
    main()
