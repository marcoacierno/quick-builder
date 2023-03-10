
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
        subprocess.run([
            'git', 'pull', 'origin', 'main'
        ], cwd='./tmp')
        return

    person = payload['sender']['login']

    if person != 'marcoacierno' and person != 'estyxx':
        return

    asyncio.create_task(build_lib(commit_hash, ref, person))
    return JSONResponse({'status': 'ok'})

async def build_lib(commit_hash: str, branch_ref: str, person: str):
    github = Github(GITHUB_ACCESS_TOKEN)
    repo = github.get_repo("pythonitalia/pycon-styleguide")
    pulls = repo.get_pulls(head=branch_ref)
    pull_req = next(
        (pull for pull in pulls
        if pull.head.sha == commit_hash),
        None
    )
    if not pull_req:
        pulls = repo.get_pulls(head=branch_ref)
        pull_req = next(
            (pull for pull in pulls
            if pull.head.sha == commit_hash),
            None
        )

    if not pull_req:
        return

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

    work_dir = "./tmp-marco" if person == "marcoacierno" else "tmp"
    try:
        subprocess.run([
            'git', 'fetch'
        ], cwd=work_dir)

        subprocess.run([
            'git', 'checkout', branch_ref.replace('refs/heads/', '')
        ], cwd=work_dir)

        subprocess.run([
            'git', 'reset', '--hard', f"origin/{branch_ref.replace('refs/heads/', '')}"
        ], cwd=work_dir)

        subprocess.run([
            'pnpm', 'version', 'patch', '--no-git-tag-version'
        ], cwd=work_dir)

        with open(f'{work_dir}/package.json', 'r') as f:
            package_json = f.read()
            new_version = json.loads(package_json)['version']
            pr_version = f'{new_version}-pr{commit_hash}'

        result = subprocess.run([
            'pnpm', 'version', pr_version, '--no-git-tag-version'
        ], cwd=work_dir)

        if result.returncode != 0:
            raise Exception("Unable to up version")

        result = subprocess.run([
            'pnpm', 'run', 'build'
        ], cwd=work_dir, stdout=subprocess.PIPE)

        if result.returncode != 0:
            raise Exception("Build failed: " + result.stdout.decode('utf-8'))

        result = subprocess.run([
            'pnpm', 'publish', '--tag', 'pr', '--no-git-checks'
        ], cwd=work_dir)

        if result.returncode != 0:
            raise Exception("Unable to publish")

        message = f"""
# Pre-release
:wave:

Pre-release **{pr_version}** [{commit_hash}] has been released on NPM! :rocket:

You can try it by doing:

```shell
pnpm add @python-italia/pycon-styleguide@{pr_version}
```
"""
    except Exception as exception:
        message = f"""
# Pre-release
:wave:

Something went wrong while trying to build [{commit_hash}]
"""


    found_comment.edit(message)


app = Starlette(debug=True, routes=[
    Route('/github', github_webhook, methods=['POST']),
])

