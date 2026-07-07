#!/usr/bin/env python3
import boto3

# SPACES_KEY = 'DO801Y92Z7K4PJ4HLKM7'
# SPACES_SECRET = 'DqTEk9/ddeqNewJuHm5j7Hv3mbChllTNN8w+c3J4n9A'
SPACES_BUCKET = 'staticmediacontents'

SPACES_KEY='DO00L9NPAZJCKQ3WCJCM'
SPACES_SECRET='CRTIFfz6oyYafB9HOErjUiybwgt4LKEwf06hRp0+Hw0'
s3 = boto3.client('s3', endpoint_url='https://sfo3.digitaloceanspaces.com',
                  aws_access_key_id=SPACES_KEY,
                  aws_secret_access_key=SPACES_SECRET)

# List all objects + make public
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket=SPACES_BUCKET):
    for obj in page.get('Contents', []):
        key = obj['Key']
        s3.copy_object(
            Bucket=SPACES_BUCKET,
            Key=key,
            CopySource={'Bucket': SPACES_BUCKET, 'Key': key},
            ACL='public-read',
            MetadataDirective='REPLACE'
        )
        print(f'✅ PUBLIC: {key}')
print('🎉 ALL FILES PUBLIC!')
