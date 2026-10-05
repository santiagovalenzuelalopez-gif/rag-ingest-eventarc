"""Envía un CloudEvent de GCS al servicio local, igual que Eventarc.

Uso:
    python scripts/send_event.py finalized demo/knowledge/faq.md --generation 1
    python scripts/send_event.py deleted   demo/knowledge/faq.md --generation 1
    curl localhost:8000/demo/state     # ver documentos y tracking (solo backend memory)
"""

import argparse
import json

import httpx

TYPES = {
    "finalized": "google.cloud.storage.object.v1.finalized",
    "deleted": "google.cloud.storage.object.v1.deleted",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=TYPES)
    parser.add_argument("object_name", help="<tenant_id>/knowledge/<ruta>")
    parser.add_argument("--bucket", default="tenants-bucket")
    parser.add_argument("--generation", type=int)
    parser.add_argument("--url", default="http://localhost:8000/events/gcs")
    args = parser.parse_args()

    body = {"bucket": args.bucket, "name": args.object_name}
    if args.generation is not None:
        body["generation"] = str(args.generation)

    response = httpx.post(
        args.url,
        content=json.dumps(body),
        headers={
            "ce-specversion": "1.0",
            "ce-id": "local-1",
            "ce-source": f"//storage.googleapis.com/projects/_/buckets/{args.bucket}",
            "ce-type": TYPES[args.kind],
            "content-type": "application/json",
        },
    )
    print(response.status_code, response.text or "(sin cuerpo)")


if __name__ == "__main__":
    main()
