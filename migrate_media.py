#!/usr/bin/env python3
import boto3
import os
from pathlib import Path

# REPLACE THESE WITH YOUR ACTUAL KEYS
# SPACES_KEY = 'DO801Y92Z7K4PJ4HLKM7'  # Your Spaces Access Key
# SPACES_SECRET = 'DqTEk9/ddeqNewJuHm5j7Hv3mbChllTNN8w+c3J4n9A'  # Your Spaces Secret Key

SPACES_BUCKET = 'staticmediacontents'

SPACES_KEY='DO00L9NPAZJCKQ3WCJCM'
SPACES_SECRET='CRTIFfz6oyYafB9HOErjUiybwgt4LKEwf06hRp0+Hw0'
# SPACES_KEY='DO00L9NPAZJCKQ3WCJCM'
# SPACES_SECRET='CRTIFfz6oyYafB9HOErjUiybwgt4LKEwf06hRp0+Hw0'
SPACES_ENDPOINT = 'sfo3.digitaloceanspaces.com'
# SPACES_BUCKET = 'peopleskilltraining-media'

s3 = boto3.client(
    's3',
    endpoint_url=f'https://{SPACES_ENDPOINT}',
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET
)

media_dir = Path('media')
total = 0
uploaded = 0

print('🔄 Scanning media files...')
for file_path in media_dir.rglob('*'):
    if file_path.is_file():
        total += 1
        key = f'media/{file_path.relative_to(media_dir)}'
        
        print(f'📤 Uploading {key}...')
        try:
            s3.upload_file(str(file_path), SPACES_BUCKET, key)
            uploaded += 1
            print(f'✅ {key}')
        except Exception as e:
            print(f'❌ {key}: {e}')

print(f'\n🎉 Migration complete: {uploaded}/{total} files uploaded!')
