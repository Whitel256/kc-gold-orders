"""
Cloud image storage (Cloudflare R2 / any S3-compatible bucket).

Local disk storage doesn't survive restarts/redeploys on Render,
Railway, Heroku, etc. -- those platforms wipe the filesystem on every
deploy. This module uploads images to R2 instead and returns a public
URL, which gets stored in MySQL exactly like the old local path was.

Required env vars (set these in Render's dashboard, not in code):
    R2_ACCOUNT_ID
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET_NAME
    R2_PUBLIC_URL      e.g. https://pub-xxxxxxxx.r2.dev
                        (or your custom domain attached to the bucket)
"""
import os
import uuid
import boto3
from botocore.client import Config

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _client():
    account_id = os.environ['R2_ACCOUNT_ID']
    return boto3.client(
        's3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def upload_image(file_storage, folder='orders'):
    """
    Uploads a werkzeug FileStorage (from request.files) to R2.
    Returns the full public URL on success, or None if the file
    extension isn't allowed.
    """
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None

    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    key = f"{folder}/{uuid.uuid4()}.{ext}"

    bucket = os.environ['R2_BUCKET_NAME']
    content_type = file_storage.mimetype or 'application/octet-stream'

    _client().upload_fileobj(
        file_storage,
        bucket,
        key,
        ExtraArgs={'ContentType': content_type},
    )

    public_base = os.environ['R2_PUBLIC_URL'].rstrip('/')
    return f"{public_base}/{key}"


def delete_image(url_or_path):
    """
    Deletes an image from R2 given its public URL. Safe no-op if the
    value doesn't look like an R2 URL (e.g. an old local path from
    before this migration) -- those just get dropped from the DB list.
    """
    public_base = os.environ.get('R2_PUBLIC_URL', '').rstrip('/')
    if not public_base or not url_or_path.startswith(public_base):
        return
    key = url_or_path[len(public_base):].lstrip('/')
    try:
        bucket = os.environ['R2_BUCKET_NAME']
        _client().delete_object(Bucket=bucket, Key=key)
    except Exception:
        pass
