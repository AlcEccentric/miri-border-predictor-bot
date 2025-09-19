import boto3
import json
from config import R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT, R2_BUCKET

def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )

def read_json_file(key: str):
    client = get_r2_client()
    resp = client.get_object(Bucket=R2_BUCKET, Key=key)
    return json.loads(resp["Body"].read())

def get_file_timestamp(key: str):
    """Get the last modified timestamp of a file in R2"""
    client = get_r2_client()
    resp = client.head_object(Bucket=R2_BUCKET, Key=key)
    return resp["LastModified"]