# Public repository export / 公开仓库导出

The maintenance command exports a selected local Git revision into a **new directory**. It never
pushes, creates a hosted repository or changes the source commits, index or tracked worktree.
Uncommitted source changes are not included. Finish and commit the relevant work first.

维护命令将指定的本地 Git 版本导出到**新目录**，不推送、不创建远程仓库，不改源仓提交、索引或已跟踪文件。
未提交的代码不进入导出；先完成验证并提交需要发布的改动。

```sh
uv run python scripts/export_public.py --source . --out ../datakeel-public --mode history --ref main
```

`history` keeps the selected revision's reachable code history, removes excluded material and
commits made empty by removal, applies reviewed literal replacements and explicit commit-message
mappings, and normalizes both author and committer identities. `snapshot` applies the same policy
and produces one commit. The temporary maintenance tool runs through `uvx --from git-filter-repo`;
it is not an application dependency. Its first use may download the tool.

`history` 保留所选版本可达的代码历史，移除排除内容及因此变空的提交，应用经审查的文本和提交信息映射，
统一作者与提交者身份；`snapshot` 使用相同策略，只输出一个提交。维护工具通过 `uvx` 临时运行，首次使用
可能下载工具，不进入项目运行依赖。

The private checkout supplies four policy files in its scripts directory: `public-exclude.txt`,
`public-replace.txt`, `public-message-map.json` and `public-scan-allow.txt`. The first three are
intentionally excluded from the public copy. To use the command from a public copy, provide an
independently reviewed policy directory with `--policy-dir`. Arbitrary scan exemptions are rejected;
only dependency-lock checksum fields are eligible. Replacement rules are finite, reviewed entries;
new unexpected sensitive content must still fail the scan.

私有工作副本提供四份策略文件；排除清单、历史文本替换表与原提交映射自身也不进入公开版。从公开副本运行
维护命令时，需用 `--policy-dir` 指定另行审查的策略目录。不接受任意扫描豁免，仅依赖锁文件的校验值字段
可豁免；替换表只列已核对的有限条目，新增的意外敏感内容仍会导致失败。

Every retained commit is scanned, including its filenames, file contents, commit message and
identity metadata. Binary assets receive filename and size checks; text receives the full rules.
The report lists image paths for visual review. A nonzero exit or `success: false` means the export
must not be published. Findings identify the commit, file, line and rule without copying secret
values into the report. Failed output is retained for inspection; choose another new directory to retry.

扫描遍历全部保留提交的文件名、正文、提交信息及身份元数据。二进制资源检查文件名和大小，文本执行全部
规则；报告列出图片路径，供人工看图。非零退出码或 `success: false` 表示导出未通过。命中记录包含提交、
文件、行号和规则，不重复输出密钥值。失败目录保留供检查，重试需选择另一个新目录。

The JSON report is stored at `.git/public-export-report.json`, outside versioned content. It includes
source, removed-empty and retained commit counts; snapshots additionally report the number collapsed.
Validate a successful export in a separate fresh clone before publication:

JSON 报告位于 `.git/public-export-report.json`，不属于可发布的已跟踪内容，包含源提交数、删除的空提交数、
保留提交数；快照另列折叠数量。发布前从成功导出的仓库创建全新克隆，独立安装并验证：

```sh
git clone --no-local ../datakeel-public ../datakeel-public-check
cd ../datakeel-public-check
uv sync --locked
(cd web && npm ci)
make check
```

The security and community reporting contacts remain maintainer-supplied release prerequisites.
Exporting does not publish anything or fill in those contacts.

安全与社区问题的私下联系方式仍由维护者在公开发布前填写。导出不会发布仓库，也不会代填这些联系方式。
