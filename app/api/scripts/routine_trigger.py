"""Authenticated manual trigger. Reads credentials from environment, never command arguments."""
import argparse
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("kind")
    parser.add_argument("--save",action="store_true",help="Store the result; default is dry run.")
    parser.add_argument("--task-id")
    parser.add_argument("--starts-at")
    args=parser.parse_args()
    root=os.environ.get("YGGDRAS_APP_URL","http://127.0.0.1:3000").rstrip("/")
    url=urlsplit(root)
    if url.scheme!="https" and not (url.scheme=="http" and url.hostname in ("127.0.0.1","localhost")):
        parser.error("Use HTTPS or loopback.")
    # An existing phone token is supported by the same authenticated backend.
    token=os.environ.get("YGGDRAS_APP_SESSION","")
    if not token:
        parser.error("Set YGGDRAS_APP_SESSION to a private mobile sign-in token.")
    body={"kind":args.kind,"dry_run":not args.save}
    if args.task_id:
        body["task_id"]=args.task_id
    if args.starts_at:
        body["starts_at"]=args.starts_at
    request=Request(root+"/api/backend/application/daily-routines/trigger",
        data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+token,"Origin":root})
    with urlopen(request,timeout=60) as response:
        print(response.read().decode())


if __name__=="__main__":
    main()
