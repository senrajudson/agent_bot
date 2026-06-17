from __future__ import annotations

import argparse
from pathlib import Path

from app.bridge.google_chat.media_downloader import GoogleChatMediaDownloader
from app.bridge.google_chat.parser import parse_google_chat_event
from app.bridge.google_chat.pubsub_subscriber import GoogleChatPubSubSubscriber


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lê uma mensagem do Pub/Sub e baixa imagens anexadas do Google Chat."
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout aguardando mensagem no Pub/Sub.",
    )

    parser.add_argument(
        "--output-dir",
        default="/tmp/google_chat_images",
        help="Diretório para salvar imagens baixadas.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    subscriber = GoogleChatPubSubSubscriber()

    payload = subscriber.listen_once(
        timeout_seconds=args.timeout,
        ack=False,
    )

    if payload is None:
        print("Nenhuma mensagem recebida.")
        raise SystemExit(1)

    event = parse_google_chat_event(payload)

    print("Mensagem:", event.message_name)
    print("Texto:", event.clean_text)
    print("Attachments:", len(event.attachments))

    for index, attachment in enumerate(event.attachments, start=1):
        print()
        print(f"Attachment {index}:")
        print("  name:", attachment.name)
        print("  content_name:", attachment.content_name)
        print("  content_type:", attachment.content_type)
        print("  source:", attachment.source)
        print("  has_resource_name:", bool(attachment.resource_name))
        print("  is_image:", attachment.is_image)
        print("  can_download_with_chat_api:", attachment.can_download_with_chat_api)

    downloader = GoogleChatMediaDownloader()
    images = downloader.download_images_from_event(event)

    print()
    print("Imagens baixadas:", len(images))

    for index, image in enumerate(images, start=1):
        suffix = _suffix_from_content_type(image.content_type)
        filename = image.filename or f"image_{index}{suffix}"

        if not Path(filename).suffix:
            filename = f"{filename}{suffix}"

        output_path = output_dir / f"{index}_{Path(filename).name}"

        output_path.write_bytes(__import__("base64").b64decode(image.base64_data))

        print()
        print(f"Imagem {index}:")
        print("  filename:", image.filename)
        print("  content_type:", image.content_type)
        print("  size_bytes:", image.size_bytes)
        print("  base64_length:", len(image.base64_data))
        print("  saved_to:", output_path)


def _suffix_from_content_type(content_type: str) -> str:
    normalized = content_type.lower().strip()

    if normalized == "image/png":
        return ".png"

    if normalized in {"image/jpeg", "image/jpg"}:
        return ".jpg"

    if normalized == "image/webp":
        return ".webp"

    return ".bin"


if __name__ == "__main__":
    main()