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
| `video.probe` | No parameters; duration, frame rate, resolution, codec, rotation, audio-track count. A file whose header promises noticeably (over 500 ms) more than its stored packets contain reports the readable `duration_ms`, the promise as `declared_duration_ms`, and a critical `truncated_file` interval for the missing tail / 无参数，读取录制属性；头部声明比实际可读多出 500ms 以上时报实际时长、声明时长和缺失尾段的 `truncated_file` 问题 |
| `video.invalid_frames` | `sample_fps`, `black_threshold`, `solid_std_threshold`, `freeze_difference`, `freeze_local_difference`, `freeze_locality`, `freeze_noise_ratio`, `freeze_duration_ms`, `blur_variance_threshold`, `minimum_interval_ms`, `remove`, `invalid_ratio_threshold`; each frame gets its most specific defect (black, else uniform, else blurred). A frame continues a freeze only when no 16x9 block changed by more than `freeze_local_difference` (and `freeze_locality` times the frame-wide change), the frame-wide change stays below `freeze_noise_ratio` of the recording's median change, and it still matches the first held frame; a keyframe re-encoding the held picture does not end it / 黑、纯色、冻、模糊区间，每帧只记最具体的一类；冻结要求没有分块局部变化、全局变化低于本录制噪声底且与冻结首帧一致，关键帧重编码不打断冻结 |
| `video.dedup` | `window_ms`, `sample_fps` (maximum analysis rate; slower video is compared frame by frame), `max_hamming`, `max_brightness_difference`, `max_spatial_difference`, `max_local_difference`, `minimum_clip_ms`, `remove`; a repeat must reproduce how the picture changes, not only how it looks: windows that are mostly static are never matched, matched frames must reproduce the ~100 ms motion (uniform brightness change removed), and content that recurs within three windows of itself (a blinking light, a clock's sub-second digits) is periodic, not repeated. Windows are searched at every prior frame offset and each match is extended frame by frame, so repeats of at least 1.5 windows are located wherever they start / 重复必须重现画面变化：大部分静止的窗口不比，运动须吻合，附近反复出现的周期内容不算重复；在任意帧偏移处查找并逐帧扩展到真实起止 |
| `video.segment` | `window_ms`, `minimum_duration_ms`, `skip_issues`; fixed-window clips on frame times read from packet timestamps, each decoded from the nearest earlier keyframe, optionally only inside ranges without annotated issues / 按包时间戳定帧的固定窗口切片，从最近关键帧解码；可只切不含已标问题的区间 |
| `video.normalize` | `width`, `height`, `frame_rate`; MPEG-4/AAC MP4, letterboxing and square pixels; measured issue intervals carry over because the timeline is unchanged / 统一编码、分辨率与帧率，时间轴不变故沿用已测问题区间 |
| `audio.probe` | No parameters; duration, sample rate, channels and codec; truncation is reported as for video, using the WAV data chunk size when present / 无参数，读取音轨属性；截断同视频，WAV 以 data 块声明为准 |
| `audio.vad` | `threshold_dbfs`, `frame_ms`, `min_activity_ms`, `min_silence_ms`; energy activity intervals / 能量活动区间 |
| `audio.trim_silence` | Activity parameters plus `padding_ms`; trim edges while preserving internal timing, remove wholly silent files / 裁首尾静音，保留内部时间顺序 |
| `audio.loudness` | `acceptable_min_lufs` (-23), `acceptable_max_lufs` (-14), `loudness_tolerance_lu` (1), `target_lufs` (-23, the normalization target), `true_peak_dbfs`, `loudness_range_lu`, `normalize`; EBU R128 measurement, a flag only when integrated loudness lies more than the tolerance outside the accepted range, and optional two-pass normalization. The range, tolerance and deviation are stored in `audio_metrics` and printed in the report / 响度落在可接受区间（默认 -23 到 -14 LUFS，各留 1 LU 容差）外才报；区间、容差和偏离写进指标与报告；可选两遍归一到 `target_lufs` |
| `audio.clipping` | `threshold`, `min_consecutive_samples`, `saturation_level`, `saturation_occupancy`, `window_ms`, `merge_gap_ms`; flat full-scale plateaus (a run that moves, such as a lossy decoder's overshoot, is not one) plus windows that dwell near full scale (lossy-coded clipping), merged per passage / 满幅平坦平台（有损解码的过冲在动，不算）加近满幅驻留（有损编码后的削波），按段合并 |
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

## Long recordings, failures and limits / 长录制、单文件失败与边界

Every video is decoded once, multithreaded, into per-frame statistics and 32x18
thumbnails that invalid-frame detection and deduplication share; frames are streamed
and reduced, never held in memory at full size. Clips enter the file just before the
last keyframe at or before their start (read from the packet flags) and drop earlier
frames exactly, so each decodes from that keyframe instead of from the start of the
file, also in MPEG-TS, which has no seek index. Command
time limits scale with the recording: `base + ratio x seconds x max(1, pixels /
1080p)`, capped. Configure with `DATAKEEL_MEDIA_TIMEOUT_BASE_SECONDS` (300),
`DATAKEEL_MEDIA_TIMEOUT_RATIO` (2), `DATAKEEL_MEDIA_TIMEOUT_MAX_SECONDS` (21600) and
`DATAKEEL_MEDIA_THREADS` (0 = CPU count, at most 8). Encoders run on one thread so
artifact bytes do not depend on the machine. Repeat search compares earlier frames in
fixed-size blocks and thumbnails become luma in blocks, so video memory grows only with
the per-frame summaries, about 10 KB per analysed frame.

A recording that cannot be read or processed is kept with a `media_failure` record
(operator and reason) and passed through the remaining operators untouched; the other
recordings are processed and published. A task whose every output failed fails; one
with some failures completes as partial: the task view (`partial`, `failed_files`),
the quality summary (`failures`, `partial`), the report chapter and `demo-media`
list each failed recording. Failed recordings are not scored.

视频只解码一遍（多线程），无效帧与去重共用逐帧统计和缩略图；切片在输入端定位，从
最近关键帧解码。命令超时随时长与分辨率伸缩并封顶，可用上述环境变量配置；编码器单线程，
产物与机器核数无关。重复搜索和亮度换算都分块进行，视频内存只随逐帧摘要增长，每个分析帧
约 10 KB。读不了或处理失败的录制保留并记下算子与原因，其余录制照常处理和
发布；全部失败则任务失败，部分失败则任务完成但标为部分完成，任务视图、质量摘要、报告
和演示输出都列出失败清单，失败文件不计分。

Known limits / 已知边界:

- A camera whose noise the encoder removed completely shows identical frames; it is
  reported frozen, as no signal tells it from a frozen feed. A change smaller than
  `freeze_local_difference` (for example a thin clock digit changing two strokes) does
  not end a freeze. / 编码器把噪声完全抹平的静止画面与冻结无法区分，会报冻结；小于
  分块阈值的变化（如细笔画时钟只变两笔）不打断冻结。
- Thumbnails cannot resolve on-screen text, so footage differing only in a timestamp
  overlay is a repeat; synthetic test patterns that loop (`testsrc2` every 12 s) are
  reported as repeats. A clock with sub-second digits is periodic, but a window within
  two windows of the end of the recording, right after a tens-digit change, may still
  match once. / 缩略图看不清字幕，只差时间戳的画面算重复；循环的测试图样会报重复；
  毫秒时钟在片尾两窗口内恰逢十位进位时可能残留一次匹配。
- Loops that repeat three or more times with a period no longer than the window are
  periodic content and are not reported. / 周期不超过窗口且重复三次以上的循环视为
  周期内容，不报重复。
- Lossy clipping is found by dwelling near full scale. Measured recall on hard-clipped
  sines (100 Hz-3 kHz, 1.25-4x over full scale) is 0.98-0.99 for WAV, MP3 and AAC at
  128 kbit/s, with up to one 20 ms window of overhang; loud unclipped sines and pink
  noise produce no flag. Signals that are flat-topped by design (square waves) are
  indistinguishable from clipping and are flagged; clipping shorter than one window or
  softened below `saturation_level` by heavy compression is missed. / 有损削波靠近满幅
  驻留识别：硬削波正弦在 WAV/MP3/AAC 128k 下召回 0.98–0.99，边界最多多出一个 20ms
  窗口；响亮未削波信号不报。方波这类本身平顶的信号会被报；短于一个窗口或被强压缩到
  `saturation_level` 以下的削波会漏。
- The default loudness range runs from the EBU R128 broadcast target (-23 LUFS) to the
  -14 LUFS normalization of the loudest common streaming platforms, each widened by
  R128's +/-1 LU tolerance; for broadcast delivery set both ends to -23. / 默认响度区间
  从 EBU R128 广播目标 -23 LUFS 到主流流媒体归一的 -14 LUFS，两端各留 R128 的 ±1 LU
  容差；广播交付把两端都设成 -23。
- Audio operators hold the decoded track in memory (16 kHz float64 for activity,
  trimming and fingerprints; the source rate in float32 for clipping), so their memory
  grows with duration: fingerprinting a 30-minute mono recording peaks at about 2.4 GB.
  / 音频算子把整条音轨解码进内存，内存随时长线性增长：30 分钟单声道录音做指纹去重峰值
  约 2.4 GB。

## Quality, provenance and recovery / 质量、血缘与恢复

The existing five dimensions remain completeness, consistency, uniqueness,
annotation and distribution. Invalid-signal interval unions reduce completeness,
measured against the declared duration for a truncated file; loudness deviations
reduce consistency; duplicates reduce uniqueness. Annotation
without evidence remains excluded, with normalized remaining weights. Reports add
original duration, effective derived duration, clip/duplicate counts, issue
frequencies, and each file/clip's score and measured deduction reasons.

五维评分保留原定义。无效区间取并集扣完整性（截断文件按声明时长计），响度偏离扣一致性，重复扣唯一性；无标注
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
