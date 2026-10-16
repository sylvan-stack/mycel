# Stored code overview

Every complete repository pass reconciles one index section per directory that
contains an indexed on-disk code file. Empty files and files without named
symbols appear by filename. Branch and stash versions do not contribute.
The overview reads stored file, location and chunk metadata; it neither reads
unchanged source files nor calls a model or network service.

Directories and files sort by Unicode relative path. Classes sort by name and
source position; each class displays its first eight methods in source order,
with an exact omitted count. Each file also displays its first eight other
named declarations in source order, with an omitted count. The `symbols` count
includes all named declarations, including omitted ones, and excludes unnamed
module runs and artificial class continuation chunks. Declaration kind,
class membership and displayed order participate in the rendered text.

```sh
mycel overview --repo cellar
mycel overview --repo cellar --dir src/net
mycel overview --repo cellar --dir .
mycel read 'cellar:@index/overview#src%2Fnet' --no-fresh
```

`overview` accepts one enabled repository, explicitly or from its configured
folder. Organizations and repeated selectors are refused. `--dir` normalizes
a relative directory inside the code root; `.` selects the root. Absolute
paths, empty values, NUL and paths escaping the root are `invalid_input`.
A valid absent directory returns an empty list with exit status 0.

The reply is `{repository, sections}`. Each section has `directory`, `files`,
`symbols` and its complete Markdown `text`, identical to the embedded text.
Reporting uses one read-only store snapshot. It needs no source folders to
be present when the repository is explicit, runs no freshness pass, creates
no sections or activity, and requests no embedding credentials or provider.

The pass reconciles the outline after its applied code, dependency and
mechanical detection changes, in the same guarded repository transaction.
A refused or interrupted publication rolls all its outline changes back.
Previously committed repositories remain complete if a later repository fails.
An unchanged rendered section preserves its logical identity, exact text
version and vectors even after body-only code edits. A structural change
replaces the current text; its new version is pending for ordinary embedding.
Empty directories are removed. A later quiet pass rebuilds a missing section
from retained records without reparsing unchanged files.

Overview chunks have origin `overview`, root `index`, path `overview` and the
relative directory as their name. They have no file, dependency or relation
edges, generated request evidence, stale marks or Drift work. They are
excluded from summary membership. Ordinary `embed` and explicit
`ingest --embed` use the document embedding rules for their complete text.

Document-capable searches let the searched repository's overview compete
under the usual document margin and limit. Code-only searches exclude it;
shared document selections never supply another repository's overview.
Search results and citations carry canonical index addresses, stable IDs,
origin `overview` and no file or source lines. The overview never supplies a
`documentedIn` bridge to code. File references to an index overview remain
visible generated-text faults, and `derive`/`relate` refuse it as an endpoint.
