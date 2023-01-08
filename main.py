
import os
import json

import asyncio
import subprocess
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.requests import Request
from github import Github

GITHUB_ACCESS_TOKEN = os.getenv('GITHUB_ACCESS_TOKEN')


async def github_webhook(request: Request) -> JSONResponse:
    payload = await request.json()
    ref = payload['ref']
    commit_hash = payload['after']
    print('payload', payload)

    if ref == 'refs/heads/main':
        return

    asyncio.create_task(build_lib(commit_hash, ref))
    return JSONResponse({'status': 'ok'})

async def build_lib(commit_hash: str, branch_ref: str):
    github = Github(GITHUB_ACCESS_TOKEN)
    repo = github.get_repo("pythonitalia/pycon-styleguide")
    pulls = repo.get_pulls(head=branch_ref)
    pull_req = pulls[0]
    pull_request_id = pull_req.number
    issue = repo.get_issue(number=pull_request_id)
    found_comment = None

    for comment in issue.get_comments():
        if comment.user.login != 'pythonitaliabot':
            continue
        found_comment = comment

    message = f"""
# Pre-release
:wave:
Releasing commit [{commit_hash}] to NPM as pre-release! :package:
"""

    if found_comment is None:
        found_comment = issue.create_comment(message)
    else:
        found_comment.edit(message)

    subprocess.run([
        'git', 'fetch'
    ], cwd='./tmp')

    subprocess.run([
        'git', 'checkout', commit_hash
    ], cwd='./tmp')

    subprocess.run([
        'pnpm', 'version', 'patch', '--no-git-tag-version'
    ], cwd='./tmp')

    with open('./tmp/package.json', 'r') as f:
        package_json = f.read()
        new_version = json.loads(package_json)['version']
        pr_version = f'{new_version}-pr{commit_hash}'

    subprocess.run([
        'pnpm', 'version', pr_version, '--no-git-tag-version'
    ], cwd='./tmp')

    print("run build")
    subprocess.run([
        'pnpm', 'run', 'build'
    ], cwd='./tmp')

    print("publish")
    subprocess.run([
        'pnpm', 'publish', '--tag', 'pr', '--no-git-checks'
    ], cwd='./tmp')


    message = f"""
# Pre-release
:wave:

Pre-release **{pr_version}** [{commit_hash}] has been released on NPM! :rocket:

You can try it by doing:

```shell
pnpm add @python-italia/pycon-styleguide@{pr_version}
```
"""

    found_comment.edit(message)


app = Starlette(debug=True, routes=[
    Route('/github', github_webhook, methods=['POST']),
])

