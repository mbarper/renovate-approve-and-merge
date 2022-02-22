import logging
import os
import re
import sys

import github.GithubException
from github import Github

# make it possible to run these locally
# Github token should be passed through as an arg.
try:
    sys.argv[2]
except IndexError:
    # we are running locally, so put some defaults in to make it easier to run it
    GIT_TOKEN = os.environ["TOKEN"]
    ORG = "nexmoinc"
    REPO_FILTER = "terraform"
    LABEL = "rnvt_automerge"
    MERGE = True
    DEBUG = False
else:
    # We're not running locally
    GIT_TOKEN = os.environ["TOKEN"]
    ORG = sys.argv[1]
    REPO_FILTER = sys.argv[2]
    LABEL = sys.argv[3]
    MERGE = sys.argv[4] == "True" or sys.argv[4] == "1"
    DEBUG = sys.argv[5] == "True" or sys.argv[5] == "1"

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


def _get_repo_pulls(repo):
    for pull in repo.get_pulls(state="open"):
        pull.log = logging.getLogger("PULL")
        pull.real_url = pull.url.replace('api.', '').replace('repos/', '').replace('pulls', 'pull')
        if LABEL in [l.name for l in pull.labels]:
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
                pull.log.info(f"{pull.real_url} is good to merge")

                if not pull.mergeable:
                    _review_pull(pull)

                if not pull.mergeable:
                    pull.log.error(f"Approval did not make {pull.real_url} mergable")
                    continue

                if MERGE:
                    _merge_pull(pull)
