# Audio and video preprocessing / 音视频预处理

Datakeel processes recordings locally through user-installed `ffmpeg` and `ffprobe`.
Install both with `brew install ffmpeg` on macOS, or `sudo apt-get install ffmpeg`
on Debian/Ubuntu. Missing tools fail explicitly with installation guidance. Neither
binary nor new Python runtime dependencies are bundled in the wheel. Processing
uses no model service, telemetry or network media protocols.

音视频解码使用用户自行安装的 `ffmpeg` / `ffprobe`，缺失时明确报错。Datakeel 不分发
这些程序，不新增 Python 运行时依赖，也不调用模型服务。媒体输入只允许本地文件与管道。

## Run the generated example / 一条命令演示

Choose a new personal data directory, then generate, import and process the local
lavfi recordings through the normal durable worker queue:

选择新的个人数据目录，运行下列命令。生成器现场合成黑屏、冻帧、重复视频、静音，
以及延迟 500ms 的外置麦克风；任务复用正常队列、不可变版本、对象存储与血缘发布路径。

```sh
DATAKEEL_HOME=/tmp/datakeel-media-demo uv run datakeel demo-media --output /tmp/media-report.json
DATAKEEL_HOME=/tmp/datakeel-media-demo uv run datakeel api --port 8813
```

The first command prints a JSON report with dataset/task/version IDs, scores,
source ranges, operator history, alignment and measured issue intervals. Open the
local Web app, select that dataset and its processed version, then open a recording
or clip's source/quality page to see its probe, issue intervals, alignment,
processing history and clip links. Original recordings and cleaned clips remain
available in the same processed manifest. A pinned initial version has no later
measurements.

第一条命令输出报告及数据集、任务、版本 ID。Web 选择对应数据集和处理后的版本，
打开文件对象的来源或质量页，可见探测、问题区间、对齐、处理链和片段链接。原始录制与
清理后的派生片段一起保留；锁定最初版本不会借用未来版本的测量。

The demo pipeline (`datakeel.pipeline.media.media_pipeline`) runs, for video:
probe → invalid frames → duplicates → normalize → clean-range segmentation → removal
of wholly invalid clips; for audio: probe → activity → clipping → loudness →
duplicates → edge-silence trimming → re-measurement. Clips are cut only from ranges
without invalid frames or repeated content.

演示流水线视频依次为探测、无效帧、去重、归一、按干净区间切片、移除整段无效片段；音频依次为
探测、活动、削波、响度、去重、裁首尾静音后复测。切片只取不含无效帧和重复内容的区间。

To run the same chain on your own local recordings, repeat `--source`. With two or
more recordings the first one is the alignment reference.

用自己的本地录制跑同一条链时重复 `--source`；两路及以上时以第一路为对齐基准。

```sh
DATAKEEL_HOME=/tmp/datakeel-media-own uv run datakeel demo-media \
  --source helmet.mp4 --source lapel.m4a --output /tmp/own-media-report.json
```

To generate files without importing them / 仅生成素材、不导入：

```sh
uv run python scripts/generate_media.py --output /tmp/generated-media
```

## Operators and parameters / 算子和参数

All parameters reject undeclared keys and non-finite numbers.
`contracts/operators.json` exposes the complete generated schemas, bounds and
defaults. Operator version is `1.0.0` for this initial implementation.

所有参数拒绝未知字段和非有限数。完整参数上下界和默认值以生成的算子合同为准。

| Operator | Parameters and behavior / 参数与行为 |
| --- | --- |
| `video.probe` | No parameters; duration, frame rate, resolution, codec, rotation, audio-track count / 无参数，读取录制属性 |
| `video.invalid_frames` | `sample_fps`, `black_threshold`, `solid_std_threshold`, `freeze_difference`, `freeze_duration_ms`, `blur_variance_threshold`, `minimum_interval_ms`, `remove`, `invalid_ratio_threshold`; each sampled frame gets its most specific defect (black, else uniform, else blurred); a freeze needs a held picture with content / 黑、纯色、冻、模糊区间，每帧只记最具体的一类，纯色静止不算冻帧；可按无效占比移除整文件 |
| `video.dedup` | `window_ms`, `sample_fps` (maximum analysis rate; slower video is compared frame by frame), `max_hamming`, `max_brightness_difference`, `max_spatial_difference`, `minimum_clip_ms`, `remove`; windows are searched at every prior frame offset and each match is extended frame by frame, so repeats of at least 1.5 windows are located wherever they start / 在任意帧偏移处查找重复，并逐帧扩展到真实起止；可只保留唯一区间 |
| `video.segment` | `window_ms`, `minimum_duration_ms`, `skip_issues`; decoded fixed-window clips, optionally only inside ranges without annotated issues / 固定窗口切片，可只切不含已标问题的区间，记录实际源时间区间 |
| `video.normalize` | `width`, `height`, `frame_rate`; MPEG-4/AAC MP4, letterboxing and square pixels; measured issue intervals carry over because the timeline is unchanged / 统一编码、分辨率与帧率，时间轴不变故沿用已测问题区间 |
| `audio.probe` | No parameters; duration, sample rate, channels and codec / 无参数，读取音轨属性 |
| `audio.vad` | `threshold_dbfs`, `frame_ms`, `min_activity_ms`, `min_silence_ms`; energy activity intervals / 能量活动区间 |
| `audio.trim_silence` | Activity parameters plus `padding_ms`; trim edges while preserving internal timing, remove wholly silent files / 裁首尾静音，保留内部时间顺序 |
| `audio.loudness` | `target_lufs`, `true_peak_dbfs`, `loudness_range_lu`, `loudness_tolerance_lu`, `normalize`; EBU R128 measurement and optional two-pass normalization / 响度测量与可选两遍归一 |
| `audio.clipping` | `threshold`, `min_consecutive_samples`, `saturation_level`, `saturation_occupancy`, `window_ms`, `merge_gap_ms`; full-scale plateaus plus windows that dwell near full scale (lossy-coded clipping), merged per passage / 满幅平台加近满幅驻留（有损编码后的削波），按段合并 |
| `audio.dedup` | `correlation_threshold`, `shape_threshold`, `stationary_threshold`, `max_lag_ms`, `duration_tolerance`, `remove`; varying sound matches when its MFCC fluctuations correlate within the lag window (robust to gain and lossy re-encoding), steady tones by spectral shape / 变化的声音比 MFCC 起伏的相关性（抗增益和有损重编码），稳态音比频谱形状 |
| `media.align` | `max_offset_seconds`, `min_overlap_ms`, `min_correlation`, `max_secondary_ratio`, `max_analysis_seconds`; cross-correlation of both the waveform and its first difference (whitened, so a loud shared hum cannot make the lag look periodic); each must pass the same checks and the more confident success is kept; offsets relative to first input / 原波形与一阶差分（白化）分别互相关并各自过同样的检查，取置信度更高的成功结果；相对首路偏移与置信度 |

Audio VAD is an energy activity estimate: noise and music can be active. It does
not identify speech, speakers or words. Black/solid/blur/freeze thresholds refer to
sampled frames; short defects below the sampling interval may not be observed.
These are deterministic signal checks, not semantic judgments about useful footage.

VAD 是能量估计，噪声和音乐也可能被判为活动，不做语音识别或说话人识别。视频检测基于
抽样帧，短于抽样间隔的问题可能漏检；阈值判断信号特征，不判断内容语义。

For alignment, a positive `offset_ms` means the common signal occurs later in that
recording. Subtract it from that recording's timestamps to match the first input.
Silent, unrelated or ambiguous periodic signals return `aligned=false`, a null
offset and an explicit reason. Pairwise deduplication and alignment require one
shard so input partitioning cannot hide matches.

对齐正偏移表示共同信号在该路出现较晚，应从该路时间戳减去该值。静音、无共同信号或
周期歧义返回明确的无法对齐状态和空偏移，不编造偏移。去重与对齐必须单分片运行。

## Quality, provenance and recovery / 质量、血缘与恢复

The existing five dimensions remain completeness, consistency, uniqueness,
annotation and distribution. Invalid-signal interval unions reduce completeness;
loudness deviations reduce consistency; duplicates reduce uniqueness. Annotation
without evidence remains excluded, with normalized remaining weights. Reports add
original duration, effective derived duration, clip/duplicate counts, issue
frequencies, and each file/clip's score and measured deduction reasons.

五维评分保留原定义。无效区间取并集扣完整性，响度偏离扣一致性，重复扣唯一性；无标注
证据时仍排除标注维度。报告单列原始时长、有效派生时长、片段和重复数、问题分布及逐文件原因。

Derived metadata includes `source_file_id` (immediate input), `source_asset_id`
(original recording), `source_start_ms`/`source_end_ms` (original timeline), plus
versioned `media_history` with validated parameters and their digest. Artifact
identity is deterministic for the same source, parameters and output bytes. The
worker publishes per-file lineage with its normal fenced transaction. Cancellation
or a stale lease cannot publish a new manifest or transformation events; reruns
retain immutable earlier versions. Existing object retention applies to attempt
files and historical versions; cancelling a task is not physical object erasure.

派生元数据同时保留直接输入、原始资产及原始时间区间，处理链保存算子版本、参数和摘要。
相同源、参数与字节产生相同身份。血缘和产物版本在现有租约围栏事务中一起发布；取消或
失去租约的尝试不能发布新版本和血缘。重跑保留旧版本，存储沿用既有保留策略。
