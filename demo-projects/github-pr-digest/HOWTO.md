# how I actually run this

1. Put the repo names in `repos.txt`.
2. Export the GitHub token and the Slack webhook in `.env`. The dashboard should only ever show those names.
3. `python digest.py --dry-run` before posting.

TODO: group by reviewer instead of dumping a flat list.

The schedule is a comment, not a real cron job. The laptop is closed.
