from pathlib import Path
import boto3
from botocore.client import Config
from ..config import get_settings

settings = get_settings()
LOCAL_ROOT = Path("storage")


def _s3():
    if not all([settings.bucket, settings.access_key_id, settings.secret_access_key, settings.endpoint]):
        return None
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        region_name=settings.region,
        config=Config(signature_version="s3v4"),
    )


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client = _s3()
    if client:
        client.put_object(Bucket=settings.bucket, Key=key, Body=data, ContentType=content_type)
    else:
        path = LOCAL_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key


def get_bytes(key: str) -> bytes:
    client = _s3()
    if client:
        return client.get_object(Bucket=settings.bucket, Key=key)["Body"].read()
    return (LOCAL_ROOT / key).read_bytes()


def download_url(key: str, expires: int = 3600) -> str | None:
    client = _s3()
    if not client:
        return None
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.bucket, "Key": key},
        ExpiresIn=expires,
    )
