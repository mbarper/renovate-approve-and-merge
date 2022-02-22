# PR Approve and Merge
This github action essentially looks for PRs in a given organisation that have a given
label. Said label indicates to the action that the PR is to be approved and merged.

## Inputs:
```
  github_token: {{ $secret.RENOVATE_TOKEN }}
  organisation: <organisation>
  repo_filter: '.'
  label: 'rnvt_automerge'
  merge: 1
  debug: 0
```

more readme to follow