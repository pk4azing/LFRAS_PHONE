import boto3, os, io, zipfile, tempfile, mimetypes
from datetime import datetime

def s3_client():
    return boto3.client('s3', region_name=os.environ.get('AWS_REGION','us-east-1'))

def s3_key_exists(bucket, key):
    try:
        s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False

def upload_bytes(bucket, key, data: bytes, content_type=None):
    s3 = s3_client()
    extra = {}
    if content_type:
        extra['ContentType'] = content_type
    s3.put_object(Bucket=bucket, Key=key, Body=data, **extra)
    return f's3://{bucket}/{key}'

def upload_fileobj(bucket, key, fileobj, content_type=None):
    s3 = s3_client()
    extra = {}
    if content_type:
        extra['ContentType'] = content_type
    s3.upload_fileobj(Fileobj=fileobj, Bucket=bucket, Key=key, ExtraArgs=extra if extra else None)
    return f's3://{bucket}/{key}'

def presign(bucket, key, expires=3600):
    return s3_client().generate_presigned_url('get_object', Params={'Bucket':bucket,'Key':key}, ExpiresIn=expires)

def zip_and_upload(bucket, base_prefix, files: list):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.writestr(f['arcname'], f['bytes'])
    buf.seek(0)
    key = f"{base_prefix.rstrip('/')}/bundle.zip"
    upload_fileobj(bucket, key, buf, content_type='application/zip')
    return key
