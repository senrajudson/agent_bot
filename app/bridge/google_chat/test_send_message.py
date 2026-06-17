from __future__ import annotations

import argparse
import json
import os

from app.bridge.google_chat.chat_client import GoogleChatClient
from app.bridge.google_chat.config import get_google_chat_bridge_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envia uma mensagem de teste no Google Chat."
    )

    parser.add_argument(
        "--space",
        default=os.getenv("GOOGLE_CHAT_TEST_SPACE", "").strip(),
        help="Nome do space. Exemplo: spaces/AAAA...",
    )

    parser.add_argument(
        "--thread",
        default=os.getenv("GOOGLE_CHAT_TEST_THREAD", "").strip(),
        help="Nome da thread. Exemplo: spaces/AAAA.../threads/BBBB...",
    )

    parser.add_argument(
        "--text",
        default="Teste de envio pelo bridge Python.",
        help="Texto da mensagem.",
    )

    args = parser.parse_args()

    if not args.space:
        raise SystemExit(
            "Informe o space com --space ou configure GOOGLE_CHAT_TEST_SPACE no .env."
        )

    thread_name = args.thread or None

    settings = get_google_chat_bridge_settings()
    settings.validate_google_chat_config()

    client = GoogleChatClient(settings=settings)

    result = client.send_text(
        space_name=args.space,
        text=args.text,
        thread_name=thread_name,
    )

    print("Mensagem enviada com sucesso.")
    print(
        json.dumps(
            {
                "name": result.get("name"),
                "space": result.get("space", {}).get("name"),
                "thread": result.get("thread", {}).get("name"),
                "text": result.get("text"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()