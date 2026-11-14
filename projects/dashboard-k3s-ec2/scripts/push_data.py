#!/usr/bin/env python3
"""boto3 alternative to push-data.sh for the nightly DATA upload only (no AWS CLI needed).

    uv run --with boto3 scripts/push_data.py --bucket NAME [--src ../creator-calls-dashboard] [--prefix site/]

Uses the `dashboard-publisher` AWS profile (override with AWS_PROFILE). Uploads the 4 data JSON files,
skipping any whose MD5 already matches the object's ETag. For the site files (and the holdings strip),
use push-data.sh --with-site.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

DATA_FILES = ["mentions.json", "scores.json", "insights.json", "prices.json"]


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None, s3=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--src", default=os.environ.get("DASHBOARD_SRC", "../creator-calls-dashboard"))
    p.add_argument("--prefix", default="site/")
    p.add_argument("--dryrun", action="store_true")
    a = p.parse_args(argv)
    prefix = a.prefix if a.prefix.endswith("/") else a.prefix + "/"

    if s3 is None:
        import boto3  # imported here so --help works without boto3

        s3 = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "dashboard-publisher")).client("s3")

    uploaded = 0
    for name in DATA_FILES:
        path = (Path(a.src) / "data" / name).resolve()  # resolve: follows the mentions.json symlink
        with path.open() as f:
            json.load(f)  # refuse to publish broken JSON
        key = f"{prefix}data/{name}"
        digest = md5(path)
        try:
            etag = s3.head_object(Bucket=a.bucket, Key=key)["ETag"].strip('"')
        except Exception:  # missing object (404) -> upload
            etag = None
        if etag == digest:
            print(f"unchanged {key}")
            continue
        print(f"{'would upload' if a.dryrun else 'upload'} {path.name} -> s3://{a.bucket}/{key}")
        if not a.dryrun:
            # Single PUT (not multipart) so the ETag stays the plain MD5 for the next comparison.
            with path.open("rb") as body:
                s3.put_object(
                    Bucket=a.bucket, Key=key, Body=body,
                    ContentType="application/json", CacheControl="no-cache",
                )
            uploaded += 1
    print(f"done: {uploaded} uploaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
