import logging
import os
import re
import sys
import time

import github.GithubException
from github import Github

# make it possible to run these locally
# Github token should be passed through as an arg.
try:
    sys.argv[2]
except IndexError:
    # we are running locally, so put some defaults in to make it easier to run it
    GIT_TOKEN = sys.argv[1]
    ORG = "nexmoinc"
    REPO_FILTER = "terraform"
    LABEL = "rnvt-automerge"
    NO_LABEL = "rnvt-no-merge"
    MERGE = True
    DEBUG = False
else:
    # We're not running locally
    GIT_TOKEN = sys.argv[1]
    ORG = sys.argv[2]
    REPO_FILTER = sys.argv[3]
    LABEL = sys.argv[4]
    NO_LABEL = sys.argv[5]
    MERGE = sys.argv[6] == "True" or sys.argv[6] == "1"
    DEBUG = sys.argv[7] == "True" or sys.argv[7] == "1"

logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO, format='[%(levelname)s][%(name)s] %(message)s')

def _get_orgs(g):
    for org in g.get_user().get_orgs():
        try:
            org.log = logging.getLogger("ORG")
            if org.login == ORG or org.name == ORG:
                yield org
            else:
                org.log.debug(f"'{org.name}' was filtered out because it didn't match '{ORG}'")
        except github.GithubException as e:
            org.log.debug(f"No access to this org by SAML")


def _get_org_repos(org):
    for repo in org.get_repos():
        try:
            repo.log = logging.getLogger("REPO")
            if re.search(REPO_FILTER, repo.name):
                yield repo
            else:
                repo.log.debug(f"'{repo.name}' was filtered out because it didn't match '{REPO_FILTER}'")
        except github.GithubException as e:
            org.log.error("This token has not been given permissions to access these repos")

def _put_pull_attrs(pull):
    pull.log = logging.getLogger("PULL")
    pull.real_url = pull.url.replace('api.', '').replace('repos/', '').replace('pulls', 'pull')

def _refresh_pull(repo, pull):
    p = repo.get_pull(pull.number)
    _put_pull_attrs(p)
    return p

def _get_repo_pulls(repo):
    for pull in repo.get_pulls(state="open"):
        _put_pull_attrs(pull)
        if NO_LABEL in [l.name for l in pull.labels]:
            pull.log.debug(f"{pull.real_url} has '{NO_LABEL}' - ignoring")
        elif LABEL in [l.name for l in pull.labels]:
            pull.log.debug(f"{pull.real_url} has '{LABEL}' and no '{NO_LABEL}' - doing")
            yield pull
        else:
            pull.log.debug(f"{pull.real_url} was filtered out because labels didn't match")


def _review_pull(pull):
    pull.log.debug(f"Posting approval review to {pull.real_url}")
    pull.create_review(event="APPROVE")
    pull.log.info(f"Approval posted to {pull.real_url}")
    return True


def _merge_pull(pull):
    pull.log.debug(f"Merging {pull.url}")
    methods = ["squash", "rebase", "merge"]
    for method in methods:
        try:
            pull.merge(merge_method=method)
            pull.log.info(f"Merged {pull.real_url}")
            return True
        except github.Github as e:
            continue
    else:
        pull.log.error(f"Could not merge {pull.real_url}")
        return False


if __name__ == '__main__':
    log = logging.getLogger("MAIN")
    g = Github(GIT_TOKEN)
    log.debug("Fetching orgs")

    for org in _get_orgs(g):
        org.log.debug(f"Fetching repos in '{org.name}'")

        for repo in _get_org_repos(org):
            repo.log.debug(f"Fetching pulls for '{repo.name}'")

            for pull in _get_repo_pulls(repo):
                pull.log.info(f"Found {pull.real_url}")

                if not pull.mergeable:
                    pull.log.info(f"{pull.real_url} is not mergable. Posting an approval to see if that fixes it.")
                    _review_pull(pull)

                i = 0
                while not pull.mergeable:

                    # refresh the object, as the mergability doesn't seem to update
                    pull.log.debug(f"Refreshing pull object - {pull.real_url}")
                    pull = _refresh_pull(repo, pull)

                    if not i:
                        pull.log.warning(f"Approval did not make mergable.")
                    elif i < 10:
                        pull.log.warning(f"Back-off {i+1}s waiting for mergability of {pull.real_url}")
                    else:
                        pull.log.error(f"Could not make {pull.real_url} mergeable. State: {pull.mergeable_state} {pull.mergeable}")
                        pull.create_review_comment(
                            f"Attempted to automerge this PR, but couldn't because it's in a merge state: \n `{pull.mergeable_state}`, `{str(pull.mergeable)}`"
                        )
                        break
                    i += 1
                    time.sleep(i)

                else:
                    if MERGE:
                        pull.log.info(f"{pull.real_url} Mergeability State: {pull.mergeable_state}, {pull.mergeable}")
                        _merge_pull(pull)
