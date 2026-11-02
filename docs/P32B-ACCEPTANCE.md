# P32b 独立验收：FIX1 segment 计数阻断

日期：2026-11-02。基线：P32b HEAD `3fba9d8`。范围：segment+classification 的 `min_annotations` / `max_annotations` 计数，不 push。

## 打回问题与复现

`storage/production_catalog.py` 原来对全部启用组件求和，导致分类标签被误算成时间段：

1. `min=1,max=1`，1 段 + 1 标签被误算为 2 个标注并拒绝。
2. `min=2`，1 段 + 1 标签被误算为满足最低段数并通过。

## 修复

`validate_template_content` 在 segment 模板启用时只计算 `len(annotation.segments or ())`。分类标签不再参与 segment 的 min/max。非 segment 模板仍按启用组件求和，原有五组件行为不变。

前端 `web/src/features/labeling/templateContent.ts` 的 `countProblem` 同步采用同一规则，避免 UI 与服务端判定不一致。

## 回归覆盖

服务端和动作层均覆盖两个原始复现：

- max=1：1 段 + 1 标签可以保存并提交为 approved。
- min=2：1 段 + 1 标签保存被拒绝。

边界覆盖：0 段按 min 拒绝、2 段按 max=2 通过、3 段按 max=2 拒绝、3 个分类标签不影响段数；旧 box+classification 在 max=1 时仍按 1 框 + 1 标签 = 2 拒绝。

新增两条变异锚：

- `segment-classification-inflates-max-count`：恢复求和后，合法 max=1 用例失败，KILLED。
- `segment-classification-fills-min-count`：恢复求和后，min=2 拒绝保护失效，KILLED。

## 真实命令与结果

```sh
uv run pytest -q \
  tests/storage/test_production_segments.py \
  tests/actions/test_segment_counts.py \
  tests/storage/test_production_template_validation.py \
  tests/storage/test_production_keypoints.py
# 30 passed
```

```sh
cd web
npx vitest run \
  src/features/labeling/templateContent.test.ts \
  src/features/labeling/editors/SegmentEditor.test.tsx \
  src/features/labeling/editors/segments.test.ts
# 3 files, 14 passed
```

两条 FIX1 变异均为 KILLED。全仓静态门禁通过：ruff、pyright、import-linter、公开扫描（3556 文件 0 findings）和规模检查。前端 `npm run lint` 与 `npm run build` 通过，web_dist 已更新。

## 证据

- `outputs/p32b-independent-acceptance/fix1-pytest.log`
- `outputs/p32b-independent-acceptance/fix1-web-tests.log`
- `outputs/p32b-independent-acceptance/fix1-web-lint.log`
- `outputs/p32b-independent-acceptance/fix1-web-build.log`
- `outputs/p32b-independent-acceptance/fix1-mutations.json`

未执行完整两栈、全量变异或全量 Web 测试，仍由 PR CI 执行。没有已知 FIX1 未完成项。
