# Custom operators / 自定义算子

[English README](../README.md) · [中文首页](../README.zh.md) · [Tour / 导览](DEMO.en.md)

A custom operator is one Python file, reviewed through a controlled action before it can enter a pipeline. Approval fixes the complete UTF-8 source by SHA-256. Changing any byte creates a different version and requires another review. The Web **Custom operators** page supports submission, full source and static findings, approval, pipeline scheduling and sandbox run history.

自定义算子是一个 Python 文件，进入算子链之前必须走受控动作审阅。签批按完整 UTF-8 源码的 SHA-256 固定版本，任意字节改变都产生新版本并重新审批。Web 的「自定义算子」页支持提交、完整源码和静态检查审阅、签批、加入流水线以及查看沙箱运行记录。

## File contract / 文件合同

Export exactly one literal `PARAMETER_SCHEMA`, one literal `OUTPUT_METADATA_SCHEMA`, and one `run(inputs, params, ctx)` function. Both declarations use a bounded JSON Schema Draft 2020-12 subset with `type: "object"`. Supported keywords are `type`, `properties`, `required`, boolean `additionalProperties`, `enum`, `items`, numeric bounds (`minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`), string/array bounds (`minLength`, `maxLength`, `minItems`, `maxItems`), `title`, `description` and `default`. Each schema node declares one supported type; references, regular-expression patterns and combinators are rejected. Schemas are bounded to 64 KiB, 256 nodes and eight nesting levels. The host extracts declarations with Python's AST without importing or executing the code. Parameters are validated before execution; JSON Schema `default` values are descriptive and are not automatically inserted.

导出一个字面量 `PARAMETER_SCHEMA`、一个字面量 `OUTPUT_METADATA_SCHEMA` 和一个 `run(inputs, params, ctx)` 函数。两份声明使用有界的 JSON Schema Draft 2020-12 子集，根为 `type: "object"`。支持关键词为 `type`、`properties`、`required`、布尔 `additionalProperties`、`enum`、`items`、数值上下界、字符串/数组长度上下界及 `title`、`description`、`default`。每个 schema 节点声明单一受支持类型，禁止引用、正则模式和组合器。schema 最大 64 KiB、256 节点、嵌套八层。宿主仅用 Python AST 解析声明，不导入或执行用户代码。运行前校验参数；JSON Schema 的 `default` 只作说明，不自动填充。

```python
from pathlib import Path

PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {"contains": {"type": "string"}},
    "required": ["contains"],
    "additionalProperties": False,
}
OUTPUT_METADATA_SCHEMA = {
    "type": "object",
    "properties": {"kept_lines": {"type": "integer"}},
    "required": ["kept_lines"],
    "additionalProperties": False,
}


def run(inputs, params, ctx):
    result = []
    for index, item in enumerate(inputs):
        lines = Path(item["path"]).read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if params["contains"] in line]
        name = f"filtered-{index}.txt"
        Path(ctx["output_dir"], name).write_text("\n".join(kept), encoding="utf-8")
        result.append({"path": name, "metadata": {"kept_lines": len(kept)}})
    return result
```

`inputs` is a list of objects with `path`, `name` and `metadata`. Only the dataset files frozen into the approved pipeline manifest are copied into the sandbox; `path` names a read-only sandbox input. `params` is the validated JSON object. `ctx["output_dir"]` names the writable output directory. The return value is a list of objects with a basename-only `path` and JSON `metadata`. Write each file into `output_dir` before returning it. Returning an empty list is valid.

`inputs` 是包含 `path`、`name`、`metadata` 的对象列表。只把流水线冻结清单中的数据集文件复制到沙箱，`path` 指向只读沙箱输入。`params` 是已校验的 JSON 对象。`ctx["output_dir"]` 是可写输出目录。返回值为对象列表，每项含仅文件名的 `path` 和 JSON `metadata`；返回之前必须在输出目录写好文件。允许返回空列表。

The execution image includes Python's standard library, NumPy and Pillow. Do not import Datakeel internals or expect an installed host package, a host path, credentials or network access. The examples [filter_lines.py](../examples/custom_operators/filter_lines.py) and [tag_images.py](../examples/custom_operators/tag_images.py) filter generated text and attach a label to generated images. They contain no private or customer data.

执行镜像包含 Python 标准库、NumPy 和 Pillow。不得导入平台内部模块，也不能依赖宿主软件包、宿主路径、凭证或网络。示例 [filter_lines.py](../examples/custom_operators/filter_lines.py) 过滤生成的文本行，[tag_images.py](../examples/custom_operators/tag_images.py) 给生成图片加标签；均不含私有或客户数据。

## Container setup / 容器配置

Install and start a Docker-compatible runtime yourself. From the repository root, build the reviewed image and pin its content digest in the API and worker environment:

自行安装并启动 Docker 兼容运行时。在仓库根目录构建审阅过的镜像，并在 API 和 worker 的环境中固定内容摘要：

```bash
docker build -f sandbox/Dockerfile -t datakeel-sandbox-local .
export DATAKEEL_SANDBOX_IMAGE="$(docker image inspect datakeel-sandbox-local --format '{{.Id}}')"
export DATAKEEL_SANDBOX_BACKEND=container
```

The image uses the official Python slim base pinned by manifest digest and exact NumPy/Pillow versions. A local `sha256:...` image ID or a registry `name@sha256:...` reference is accepted; mutable tags are rejected. Keep the same image available to the runtime used by the worker. `DOCKER_HOST` or `DATAKEEL_SANDBOX_DOCKER_HOST` selects an explicitly authorized runtime endpoint. Neither value is passed into the sandbox.

镜像基于按 manifest 摘要固定的官方 Python slim，NumPy/Pillow 也固定版本。支持本地 `sha256:...` 镜像 ID 或镜像仓库 `name@sha256:...` 引用，拒绝可变 tag。worker 所用运行时必须能取得同一镜像。通过 `DOCKER_HOST` 或 `DATAKEEL_SANDBOX_DOCKER_HOST` 选择明确获准的运行时端点，这些值不传进沙箱。

## Review and run / 审阅与运行

1. Open **Custom operators**, enter a lowercase operator name, select `text`, `image` or `any`, and paste the complete Python file. **Submit for code review** creates a frozen action plan; it does not execute the code.
2. Read every source line, the exact code hash, parameter/output schemas and static findings. Findings such as `socket`, `subprocess`, `ctypes` and `os.system` identify review risks. Their absence is not a safety guarantee. Approve and execute the existing approval sheet to register the immutable version, or return it without registration.
3. Under **Approved versions**, select a generated dataset and supply a JSON parameter object, for example `{"contains":"keep"}`. **Run in pipeline** schedules the normal worker pipeline using `custom.<name>@<sha256>`. A separately started API needs a worker using the same configuration and data directory.
4. Refresh **Sandbox run history** to inspect successes and failures. Open the dataset's **Relations** view for the lineage event and its `code_hash`, `image_digest`, `params_digest`, resources and exit reason. Changing code and submitting it again leaves the original approved version unchanged.

1. 打开「自定义算子」，输入小写算子名称，选择 `text`、`image` 或 `any`，粘贴完整 Python 文件。「提交代码审阅」只产生冻结动作计划，不运行代码。
2. 逐行检查源码、完整代码哈希、参数/输出 schema 和静态检查。`socket`、`subprocess`、`ctypes`、`os.system` 等命中只提示审阅风险，未命中不代表安全。通过既有签批单签批并执行后才注册固定版本，也可退回而不注册。
3. 在「已批准版本」选择生成数据集并提供 JSON 参数，例如 `{"contains":"keep"}`。「在算子链中运行」通过普通 worker 流水线执行 `custom.<name>@<sha256>`。单独启动 API 时，还须以相同配置和数据目录启动 worker。
4. 刷新「沙箱运行记录」查看成功及失败。在数据集「关系」页查看血缘事件的代码哈希、镜像摘要、参数摘要、资源用量及退出原因。修改并重交代码不会改变原有批准版本。

The CLI uses the same plans and approvals. Read the submission output before copying its actual plan ID and plan digest into the approval command:

CLI 复用同一计划和签批。先阅读提交结果，再将真实计划 ID 和计划摘要填入签批命令：

```bash
uv run datakeel custom-operator submit examples/custom_operators/filter_lines.py \
  --name filter_lines --modality text
uv run datakeel custom-operator review PLAN_ID
uv run datakeel custom-operator approve PLAN_ID --digest PLAN_DIGEST
uv run datakeel custom-operator list
uv run datakeel custom-operator run CODE_SHA256 --name filter_lines \
  --dataset DATASET_ID --params '{"contains":"keep"}'
uv run datakeel worker --once
uv run datakeel custom-operator runs
```

Use `approve ... --reject --reason "..."` to reject a plan. `show CODE_SHA256 --name filter_lines` reads the complete approved version. Commands use the configured local database; approval cannot be transferred to another digest.

使用 `approve ... --reject --reason "..."` 拒绝计划。`show CODE_SHA256 --name filter_lines` 读取完整批准版本。命令使用配置中的本地数据库；签批不能挪给另一份摘要。

Custom outputs conservatively use the `files.any` slot. They can connect directly to generic file operators such as `file.empty_check`. Add a route node to narrow modality before connecting to a text/image-specific operator. The submission modality describes expected inputs; it does not grant stronger output typing.

自定义输出保守使用 `files.any` 槽位，可直接连接 `file.empty_check` 等通用文件算子。连接文本/图片专用算子之前须通过 route 节点收窄模态。提交的模态描述预期输入，不授予更强的输出类型。

## HTTP API

| Method and path / 方法与路径 | Result / 结果 |
| --- | --- |
| `POST /api/custom-operators` | `{name, code, modality}` → review `ActionPlan` / 审阅计划 |
| `GET /api/custom-operators/submissions` | Review plans and their durable status / 提交计划及持久状态 |
| `POST /api/approvals/{plan_id}` | Existing digest-bound approve/reject / 既有摘要绑定签批 |
| `POST /api/actions/{plan_id}/execute` | Existing plan execution registers the version / 执行计划注册版本 |
| `GET /api/custom-operators` | Approved versions / 已批准版本 |
| `GET /api/custom-operators/{code_hash}?name=...` | Full approved source and schemas / 完整源码与 schema |
| `POST /api/custom-operators/{code_hash}/runs` | `{dataset_id, version_id?, params, name?}` → queued pipeline `ActionRun` / 流水线动作记录 |
| `GET /api/custom-operators/runs?code_hash=...` | Sandbox attempt audit / 沙箱尝试记录 |
| `GET /api/custom-operators/configuration` | Backend, unsafe opt-in flag and image / 后端、不安全后端开关和镜像 |

## Output and lineage / 输出与血缘

The host independently validates output metadata against the reviewed schema, file count, total bytes and per-file bytes. Traversal, symlinks, special files and output outside the dedicated directory are rejected. A failed validation publishes no data output files for that attempt. Successes and failures both retain a run audit entity and a lineage event with the exit reason; only validated successful data files enter the pipeline outputs.

宿主独立校验输出元数据 schema、文件数、总大小和单文件大小。路径穿越、符号链接、特殊文件及越出专用目录的输出全部拒绝。校验失败不发布该次数据输出文件；成功及失败都会保留运行审计实体和含退出原因的血缘事件，只有校验成功的数据文件进入流水线输出。

Default limits are a 10-second execution timeout, 256 MiB memory, one CPU, 32 processes, 16 MiB input, 64 output files, 16 MiB total output, 8 MiB per output file and 16 KiB captured logs. The resource record reports measured wall time and available CPU/peak-memory accounting; unavailable measurements remain null rather than estimates. The lineage attribution records the immutable operator reference, source hash, actual image digest, parameter digest, resource record and exit reason.

默认上限为执行阶段墙钟 10 秒、内存 256 MiB、1 CPU、32 进程、输入 16 MiB、输出 64 文件、输出总计 16 MiB、单文件 8 MiB、日志 16 KiB。资源记录给出实测墙钟及可取得的 CPU/峰值内存统计，无法取得的值保留 null，不伪造估计。血缘归属包含固定算子引用、源码哈希、实际镜像摘要、参数摘要、资源记录与退出原因。

`timeout_seconds` applies to the execution phase, rather than the entire API or worker operation. Container creation and start each have a separate bounded control budget of 30 seconds; a creation timeout does not start user code. The timeout is enforced twice. Inside the container, a fixed supervisor runs as PID 1, launches the worker and kills every process in the sandbox's PID namespace when `timeout_seconds` elapses, so user code stops on time even when the runtime control plane is slow. The supervisor marks itself non-dumpable, so user code cannot trace or patch it, and it ignores signals from user code. On the host, an independent deadline of `timeout_seconds` starts once the runtime confirms the start; when it expires, the host stops polling and removes the container. After the worker returns, the supervisor also stops any remaining background processes before reporting completion, so nothing can change the outputs during validation. Preparation, runtime control calls, output collection and validation, and cleanup add overhead. `resources.wall_seconds` measures the complete sandbox call, including preparation and cleanup, so it can exceed the execution timeout; a delayed control plane can also delay removal.

`timeout_seconds` 适用于执行阶段，不是整个 API 或 worker 操作的总耗时上限。容器创建和启动各有独立且有界的 30 秒控制预算；创建超时不会启动用户代码。超时有两道执行：容器内由固定的监督进程（PID 1）启动 worker，到 `timeout_seconds` 即杀掉沙箱 PID 命名空间内的全部进程，即使运行时控制平面变慢，用户代码也按时停止；监督进程把自己设为不可转储，用户代码无法跟踪或篡改它，也忽略用户代码发来的信号。宿主另有独立期限，从运行时确认启动起计 `timeout_seconds`，到期即停止轮询并删除容器。worker 返回后，监督进程同样先停掉残留的后台进程再报告完成，校验期间没有进程能改动输出。准备、运行时控制调用、输出读取与校验、清理均有额外耗时。`resources.wall_seconds` 测量完整沙箱调用，包含准备及清理，因此可能超过执行超时；控制平面延迟也可能使删除延后。

## Security model and limits / 安全模型与边界

The default `container` backend requires a separately installed Docker-compatible runtime. It has no network, a read-only root filesystem, a non-root user, no capabilities, `no-new-privileges`, bounded memory/CPU/processes and a wall timeout. Inputs are copied into a read-only mount. Separate bounded temporary areas support output, execution status and scratch files; only validated files from `/output` can be published. These writable areas are not host-directory bind mounts. The sandbox receives a minimal environment instead of inheriting host secrets. The runtime socket, host home and platform storage are never mounted into the sandbox. Before starting the container, the backend rechecks its private volumes' ownership, local driver and tmpfs options. Cleanup uses bounded ownership checks and removal confirmation. If container deletion cannot be confirmed, its owned volumes are retained so a late daemon-side creation cannot silently recreate unlabeled volumes. After confirmed container removal, cleanup attempts to remove only that run's private temporary volumes. Runtime, host or control-plane failures can prevent cleanup; failures are logged and may leave those private resources behind. Restore the runtime, then inspect the exact recorded resource names and ownership labels before recovery. Automatic cleanup never uses a name-prefix deletion or removes resources belonging to another run. Missing runtime or an unconfigured/non-digest image fails explicitly; it never falls back to local execution.

默认 `container` 后端要求用户自行安装 Docker 兼容运行时。容器断网、根文件系统只读、使用非 root 用户、清空 capabilities、启用 `no-new-privileges`，限制内存/CPU/进程数及墙钟时间。输入复制到只读挂载；输出、执行状态和临时文件使用各自有界的临时写区，只有 `/output` 中校验成功的文件可以发布。这些可写区域不使用宿主目录绑定挂载。沙箱使用最小环境，不继承宿主密钥，不挂载运行时套接字、宿主家目录或平台存储。启动容器前，后端复核专用卷的归属、local 驱动及 tmpfs 选项。清理通过有界操作核验归属并确认删除；若无法确认容器已删除，则保留本次有归属的卷，避免 daemon 晚创建容器时静默重建无标签卷。确认容器删除后，才尽力清理本次运行的专用临时卷。运行时、宿主或控制平面故障可能阻止清理；系统记录失败日志，专用资源可能暂时遗留。恢复运行时后，须先核对日志中的精确资源名称与归属标签再处理。自动清理不按名称前缀批量删除，也不删除其他运行的资源。缺少运行时或镜像未按摘要配置时明确失败，不自动回退本机执行。

Non-OOM completion and error diagnostics are container reports: user code shares the supervisor's UID and can write a completion record before the supervisor does, so they are not safety evidence. The supervisor never replaces a record the worker wrote; the host freezes the container and validates or rejects whatever it finds. Host timeouts, kernel OOM signals and host output validation are independent; the host records the code, image and parameter attribution. An archive that user code inflates beyond its copy budget, for example with thousands of empty files, fails as `invalid_output`.

非 OOM 的完成与错误诊断属于容器报告值：用户代码与监督进程同 UID，可抢先写入完成记录，因此不能作为安全证明。监督进程不会覆盖 worker 已写的记录；宿主冻结容器后自行校验或拒绝。宿主超时、内核 OOM 信号及宿主输出校验独立执行，代码、镜像与参数归属由宿主记录。用户代码把归档撑过拷贝预算（例如写入数千个空文件）时按 `invalid_output` 失败。

**Containers share a kernel with their runtime host.** This is not a virtual-machine boundary and does not protect against vulnerabilities in the kernel, container runtime, Python, native extensions or the reviewed image supply chain. It does not prevent all side channels or guarantee fair scheduling across simultaneous jobs. Approval is code review, not proof of safety. Operators must receive only data the submitting workspace is authorized to process; outputs and metadata are untrusted content even after structural validation. Keep the runtime and image patched, use a dedicated runtime host for hostile workloads, and do not expose the local unauthenticated workspace API to untrusted users.

**容器与运行时宿主共享内核。** 这不是虚拟机边界，不防内核、容器运行时、Python、原生扩展或批准镜像供应链中的漏洞；不防所有侧信道，也不保证同时运行任务之间的公平调度。签批是代码审阅，不是安全证明。算子只能接收该工作区获准处理的数据，结构校验后的输出和元数据仍属于不可信内容。应更新运行时和镜像，对恶意工作负载使用专用运行宿主，不向不可信用户开放本地无认证工作区 API。

The `subprocess` backend is **unsafe development execution**, disabled by default. `DATAKEEL_SANDBOX_BACKEND=subprocess` and `DATAKEEL_SANDBOX_ALLOW_SUBPROCESS=true` explicitly opt in; the service logs and Web page display a prominent warning. Process resource limits do not isolate host files or network access. On macOS, the development backend samples the subprocess RSS and terminates its process group when over the limit; memory use can briefly overshoot between samples. Only an explicitly trusted local `SandboxRequest` can use this backend; it must never execute externally submitted code. Use `container` for code submitted through the platform.

`subprocess` 是**不安全的开发执行**，默认禁用。通过 `DATAKEEL_SANDBOX_BACKEND=subprocess` 与 `DATAKEEL_SANDBOX_ALLOW_SUBPROCESS=true` 显式开启，服务日志和 Web 会醒目警示。子进程资源上限不能隔离宿主文件和网络。macOS 开发后端采样子进程 RSS，超限时终止其进程组，采样间隔内内存可能短时超调；仅明确标为本地可信的 `SandboxRequest` 可使用，禁止执行外部提交代码。平台提交代码应使用 `container`。
