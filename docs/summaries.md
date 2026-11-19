# Quiet-period document maintenance

## Quiet-period maintenance

`mycel maintain --repo <name>` runs one finite check for one enabled repository.
It observes on-disk document inputs in the checkout and Artifact roots using
the ingest scan rules. First observation, edits, additions, moves and deletions
start a 15-minute wait for that repository. Changes to code alone leave the
timer alone. Any incomplete scan defers work. The first check after 15 quiet
minutes ingests, embeds pending on-disk document sections. It checks
for further edits between those steps.

The check returns `waiting`, `busy`, `retry`, `unchanged`, or `complete`.
`waiting` and `retry` report `eligibleAt`. A due check that leaves work
unfinished returns a nonzero exit status and names the stage. A failed check
waits 15 minutes before retrying the same observation. Successful observations
skip subsequent work until the inputs change. State and nonblocking locks are
private files under `~/.mycel/maintenance/`. Embedding uses the normal Mycel
credentials.

### Schedule checks on macOS

Use an installed Mycel Build that exposes `maintain --help`. From the Mycel
checkout, render a separate LaunchAgent for each repository you want to
maintain. The agent runs a check once per minute. `--config` can name an
alternate absolute Mycel settings file. Use the actual repository name in
place of `example-repo`.

```sh
maintenance_plist=$(mktemp -t mycel-maintenance)
python3 scripts/render_maintenance_launch_agent.py \
  --launcher "$HOME/.local/bin/mycel" --repo example-repo > "$maintenance_plist"
plutil -lint "$maintenance_plist"
maintenance_label=$(plutil -extract Label raw -o - "$maintenance_plist")
maintenance_destination="$HOME/Library/LaunchAgents/$maintenance_label.plist"
mkdir -p "$HOME/Library/LaunchAgents"
install -m 600 "$maintenance_plist" "$maintenance_destination"
launchctl bootstrap "gui/$(id -u)" "$maintenance_destination"
```

Inspect the loaded job with `launchctl print "gui/$(id -u)/$maintenance_label"`.
Use `launchctl bootout "gui/$(id -u)/$maintenance_label"` to stop scheduling
and remove that plist from `~/Library/LaunchAgents` to keep it off at login.
Jobs are opt-in.
