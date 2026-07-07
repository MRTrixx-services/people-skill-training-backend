#!/usr/bin/env python3
import boto3
import os
from pathlib import Path

SPACES_KEY = "DO00L9NPAZJCKQ3WCJCM"
SPACES_SECRET = "CRTIFfz6oyYafB9HOErjUiybwgt4LKEwf06hRp0+Hw0"
SPACES_ENDPOINT = "https://sfo3.digitaloceanspaces.com"
SPACES_BUCKET = "peopleskilltraining-media"

# Create client
s3 = boto3.client(
    "s3",
    endpoint_url=SPACES_ENDPOINT,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
)

# Local download folder
local_dir = Path("./local_media")
local_dir.mkdir(parents=True, exist_ok=True)

print("🔄 Fetching object list...")

paginator = s3.get_paginator("list_objects_v2")

count = 0
for page in paginator.paginate(Bucket=SPACES_BUCKET):
    for obj in page.get("Contents", []):
        key = obj["Key"]
        local_path = local_dir / key

        # Ensure folders exist
        local_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"⬇️ Downloading {key} → {local_path}")

        try:
            s3.download_file(SPACES_BUCKET, key, str(local_path))
            count += 1
        except Exception as e:
            print(f"❌ Error downloading {key}: {e}")

print(f"\n🎉 Download complete! {count} files saved to local_media/")
