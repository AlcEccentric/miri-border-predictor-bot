import boto3
import json
from botocore.exceptions import ClientError
from config import R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT, R2_BUCKET

_client = None

def get_r2_client():
    """Return a cached boto3 S3 client for R2.

    The client is reused across calls so that bulk reads (e.g. a type 5
    event with 52 idols x 2 borders = 104 files) don't pay client setup
    cost on every request.
    """
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
    return _client

def read_json_file(key: str):
    client = get_r2_client()
    resp = client.get_object(Bucket=R2_BUCKET, Key=key)
    return json.loads(resp["Body"].read())

def try_read_json_with_timestamp(key: str):
    """Read a JSON file and its Last-Modified timestamp in one request.

    Returns (data, last_modified_datetime), or (None, None) if the object
    does not exist. last_modified is timezone-aware (UTC).
    """
    client = get_r2_client()
    try:
        resp = client.get_object(Bucket=R2_BUCKET, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "NotFound"):
            return None, None
        raise
    return json.loads(resp["Body"].read()), resp["LastModified"]

def get_file_timestamp(key: str):
    """Get the last modified timestamp of a file in R2"""
    client = get_r2_client()
    resp = client.head_object(Bucket=R2_BUCKET, Key=key)
    return resp["LastModified"]
