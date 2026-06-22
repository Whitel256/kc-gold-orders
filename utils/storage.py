"""
Private cloud image storage with signed URLs.

Works with any S3-compatible storage:
  - Backblaze B2  (recommended, free tier, no card needed)
  - Cloudflare R2 (free tier, needs a card to activate)

Images are stored in a PRIVATE bucket. MySQL stores only the file key
(e.g. "orders/abc123.jpg"), never a full URL. When a page needs to
display an image, get_signed_url() generates a temporary link valid
for 15 minutes -- after that the link is useless to anyone who copied it.

Required env vars (set on Railway, not in code):
    STORAGE_ENDPOINT_URL    e.g. https://s3.us-west-004.backblazeb2.com  (B2)
                                 https://<account_id>.r2.cloudflarestorage.com (R2)
    STORAGE_ACCESS_KEY_ID   B2 Application Key ID  /  R2 Access Key ID
    STORAGE_SECRET_KEY      B2 Application Key     /  R2 Secret Access Key
    STORAGE_BUCKET_NAME     your bucket name
    STORAGE_REGION          B2 region e.g. us-west-004  /  R2: use "auto"
"""
import os
import uuid
import boto3
from botocore.client import Config

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
SIGNED_URL_EXPIRY = 900  # 15 minutes in seconds


def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def _client():
    """Build an S3-compatible boto3 client from env vars."""
    return boto3.client(
        's3',
        endpoint_url=os.environ['STORAGE_ENDPOINT_URL'],
        aws_access_key_id=os.environ['STORAGE_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['STORAGE_SECRET_KEY'],
        config=Config(signature_version='s3v4'),
        region_name=os.environ.get('STORAGE_REGION', 'auto'),
    )


def upload_image(file_storage, folder='orders'):
    """
    Upload a werkzeug FileStorage object to the private bucket.
    Returns the file KEY (not a URL) on success, or None if the
    file type isn't allowed.
    The key is what gets stored in MySQL.
    """
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None

    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    key = f"{folder}/{uuid.uuid4()}.{ext}"
    bucket = os.environ['STORAGE_BUCKET_NAME']
    content_type = file_storage.mimetype or 'application/octet-stream'

    _client().upload_fileobj(
        file_storage,
        bucket,
        key,
        ExtraArgs={'ContentType': content_type},
    )
    return key  # store this in MySQL, not a URL


def get_signed_url(key):
    """
    Generate a temporary signed URL for a private file key.
    Valid for 15 minutes. Safe no-op for old local paths (pre-migration)
    -- returns the key as-is so the template degrades gracefully.
    """
    if not key:
        return ''
    # Old local paths (e.g. "uploads/abc.jpg") -- not in cloud storage,
    # return empty so the template shows nothing rather than a broken link.
    if not key.startswith('orders/') and '/' in key:
        return ''
    # If storage isn't configured (e.g. local dev without env vars), skip.
    if not os.environ.get('STORAGE_ENDPOINT_URL'):
        return ''
    try:
        bucket = os.environ['STORAGE_BUCKET_NAME']
        url = _client().generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=SIGNED_URL_EXPIRY,
        )
        return url
    except Exception:
        return ''


def delete_image(key):
    """
    Delete an image from the private bucket by its key.
    Safe no-op if storage isn't configured or the key is an old local path.
    """
    if not key or not os.environ.get('STORAGE_ENDPOINT_URL'):
        return
    if not key.startswith('orders/'):
        return  # old local path, nothing to delete from cloud
    try:
        bucket = os.environ['STORAGE_BUCKET_NAME']
        _client().delete_object(Bucket=bucket, Key=key)
    except Exception:
        pass
