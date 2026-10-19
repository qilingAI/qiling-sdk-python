# qiling-ai-sdk 0.5.4

器灵官方 Python SDK，支持软件授权、套餐权益、设备与额度管理、API Key 快速授权、开放模型调用及任务查询。支持 Python 3.9+，基础功能仅使用标准库；官方OpenAI桥接为可选依赖，需要Python3.10+。

[官网](https://toolsoul.daniu7.cn) · [在线开发文档](https://867fas1f7s.apifox.cn/) · [AI 文档索引](https://867fas1f7s.apifox.cn/llms.txt) · [配套接入 Skills](https://github.com/qilingAI/qiling-skills)

接口已按 2026-10-19 的公开文档、当前服务规范及模型能力说明核对。官网链接用于访问网站；API 根地址由接入配置明确提供，SDK 不预设生产域名。

## 安装

从官方仓库安装固定版本：

```sh
python -m pip install "git+https://github.com/qilingAI/qiling-sdk-python.git@v0.5.4"
```

或者克隆源码后安装：

```sh
git clone https://github.com/qilingAI/qiling-sdk-python.git
cd qiling-sdk-python
python -m pip install .
```

包名为 `qiling-ai-sdk`，导入名为 `qiling_ai_sdk`；目前未发布到公共 PyPI，不要把同名来源不明的包当官方 SDK。

## 直接使用官方 OpenAI SDK

文本、图片生成和模型目录使用 OpenAI 格式，模型地址为已确认的平台根地址加 `/v1`。已有 OpenAI Chat Completions 程序，只需替换 API Key、Base URL 和 Model；不要求增加 App Key 或器灵请求号，也无需安装本 SDK。

```sh
python -m pip install openai
```

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["QILING_API_KEY"],
    base_url=os.environ["QILING_BASE_URL"],  # 完整模型 Base URL，含 /v1。
    max_retries=0,
)
result = client.chat.completions.create(
    model=os.environ["QILING_MODEL"],
    messages=[{"role": "user", "content": "你好"}],
)
print(result.choices[0].message.content)
```

Base URL 从接入配置取得，不根据官网链接猜测，不填旧 `/api/v1/open`。模型名来自 `client.models.list().data[].id`；单模型查询用 `client.models.retrieve(model_id)`。价格及能力在模型的 `qiling.config`，完整动态文档仍为平台根地址下的 `/api/v1/open/model-docs`。

流式调用保持官方用法：

```python
stream = client.chat.completions.create(
    model=os.environ["QILING_MODEL"],
    messages=[{"role": "user", "content": "你好"}],
    stream=True,
    stream_options={"include_usage": True},
)
try:
    for chunk in stream:
        if chunk.choices:
            print(chunk.choices[0].delta.content or "", end="", flush=True)
finally:
    stream.close()
```

图片使用 `client.images.generate(model=..., prompt=..., response_format="url")`，从 `result.data[]` 读取 url 或 b64_json。尺寸、张数、返回格式等以当前模型文档为准。文本 `max_tokens` 与 `max_completion_tokens` 二选一；支持的采样、思考参数按模型能力传入。

支持 Chat Completions（含SSE、函数工具/并行工具、工具结果续接、图文/音视频理解及JSON结构化输出）、图片生成/编辑/SSE、模型列表和单模型查询；按后台对应能力开关和供应商实际支持校验，Responses API尚未实现。视频仍为器灵 JSON 异步扩展，不能直接当作官方 Videos API 的文件上传接口。参数支持范围以 [Apifox](https://867fas1f7s.apifox.cn/llms.txt) 为准，官方 SDK 用法见 [OpenAI Chat Completions](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create)。

可运行 `python examples/openai_chat.py --prompt "你好"` 或加 `--stream` 使用同一套配置；示例会消耗调用余额。示例默认关闭自动重试，避免网络结果不明时重复提交；如需业务重试，可通过 `extra_headers={"Idempotency-Key": saved_business_request_id}` 传入事先保存的固定请求号。

## 器灵客户端与平台功能

本 SDK 继续提供软件授权、快速授权、调用余额、工具任务及视频扩展，运行时仅依赖标准库；上面的 OpenAI SDK 是按需单独安装的依赖。

| 客户端 | 凭证与用途 |
|---|---|
| `QilingAiClient` | 授权码取得 SDK 会话，用于软件权益、设备、普通额度、续费及文档保留的 SDK AI 视频接口 |
| `QilingOpenClient` | 用户 API Key；普通文本、图片返回标准 OpenAI JSON，另支持工具、余额和视频扩展 |
| `QilingAuthorizationClient` | 用户在浏览器确认后一次性领取 API Key，无需本地回调服务 |

账号 token、SDK token 和用户 API Key 不能互换。已登记的软件需要来源检查时，器灵客户端传 `app_key`，官方 OpenAI SDK 可设置 `default_headers={"x-qiling-app-key": registered_app_key}`；独立模型调用可省略，不需要为此新建软件。

```python
from qiling_ai_sdk import QilingOpenClient

client = QilingOpenClient(
    os.environ["QILING_BASE_URL"],  # 含 /v1 的模型 Base URL 或平台根地址均可。
    os.environ["QILING_API_KEY"],
)
result = client.chat(
    [{"role": "user", "content": "你好"}],
    model=os.environ["QILING_MODEL"],
    max_completion_tokens=1000,
)
print(result["choices"][0]["message"]["content"])
call_id = result["qiling"]["id"]  # 平台调用 ID，与 chatcmpl- 字符串不同。
```

`QilingOpenClient.chat` 是普通 JSON 方法，流式使用官方 OpenAI SDK；传 `stream=True` 会在发请求前提示改用官方 SDK。平台根地址自动用于工具和账户接口，不会把 `/v1` 重复拼接。

| 方法 | 用途 |
|---|---|
| `models()` / `model(model_id)` | 标准 object=list,data 目录 / 单个 model 对象 |
| `model_docs()` | 全部模型的动态请求 Schema、价格与限制 |
| `chat(messages, *, model, request_id=None, idempotency_key=None, **options)` | 标准choices/usage/qiling；支持tools/tool_choice/parallel_tool_calls、response_format及多模态消息 |
| `image(prompt, *, model, request_id=None, response_format=None, ...)` | 标准 created/data/qiling；支持参考图与图层扩展 |
| `video(prompt=None, *, model, content=None, request_id=None, ...)` | 器灵JSON视频任务，支持官方content参考素材、ratio、generate_audio、首尾帧及尾帧返回 |
| `estimate(kind, request)` | text/image/video 最大费用估算，不调用上游或冻结余额 |
| `model_call(call_id)` / `cancel_video(call_id)` | 查询平台调用 / 请求取消视频 |
| `balance()` / `usage(days=30, endpoint="")` / `logs(limit=50, offset=0, days=30, endpoint="")` | 调用余额、当前 Key 统计与记录 |
| `endpoints()` / `submit_task(endpoint, input="", options=None)` / `task(task_id)` | 工具目录、提交与结果查询 |
| `remove_ai(text)` | 提交去 AI 任务，再用返回的 task_id 查询 |

文本/图片的 `request_id` 和 `Idempotency-Key` 现为可选，省略时由平台生成；需要可靠业务重试时保存并复用原值，不同内容不要共用。器灵客户端可传 `idempotency_key`，也保留 `request_id` 参数。视频request_id也可省略或使用Idempotency-Key，手动重试应保留同一业务号。扩展费用在文本/图片结果 `qiling.billing`，平台调用 ID 在 `qiling.id`；视频保持顶层 id/status/billing 与 `data.video_url`。

`usage`、`logs` 和 `submit_task` 的 options 为关键字参数。去 AI 的 `remove_ai(text)` 和 `submit_task("remove_ai", input=text)` 原样提交正文，保留真实换行与空行。不要先合并段落、清洗空白或将换行换成字面量反斜杠加 n；JSON 序列化由 SDK 完成。保留文件原始换行时可用 `Path(path).read_bytes().decode("utf-8-sig")`。

模型费用使用 API Key 所属用户的调用余额，与软件普通次数额度独立，不追加 `consume_quota`。提交时只要求余额大于 0，不预扣、冻结或按估价占用余额；完成后依据可信实际用量与请求价格快照结算，可使余额为负，此时停止新调用，充值先抵欠款。estimate 只报价，不应在客户端以估价超过余额为由另做预冻结。报价已含倍率，十进制金额计算用 Decimal；费用为空表示待完成或核对，不代表免费。视频 submitting/queued/running/cancel_requested 查询同一平台 id，unknown/review 等待核对。取消被接受不代表最终取消或退款；流式断开也不表示免费，不自动新建请求重试。

模型错误采用 `{"error":{"message":...,"type":...,"param":...,"code":...}}`，器灵 SDK 将其中 error 对象保留在 `QilingAiError.detail`；旧平台接口的 detail 错误仍支持。HTTP 400 参数不支持，401 密钥无效，402 余额不足，403 权限不足，409 冲突或结果待核对。不能用 SDK refresh_token 刷新 API Key。

## 从 0.3.x 升级

模型路径从 `/api/v1/open/...` 改为 `/v1/...`。文本正文从旧 data 改读 `choices[0].message.content`，图片改读 `data[]`；目录从旧 models 改读 `data[]`，模型名是 id。平台调用 ID 和费用改读 `qiling.id/billing`。视频仍使用顶层 id；工具、余额和 API Key 快速授权路径保持不变。不要继续向已移除的旧模型路径发请求。

## 浏览器快速授权

```python
import os
from qiling_ai_sdk import QilingAuthorizationClient

authorization = QilingAuthorizationClient(
    os.environ["QILING_API_URL"],
    app_key=os.environ["QILING_APP_KEY"],
)
client = authorization.connect()
docs = client.model_docs()
```

软件传入平台登记的正式 App Key，平台检查软件已启用、已上架且有可用 AI 套餐配置，不再要求 API Key 账号持有该软件授权。软件可由 A 账号登录，再由 B 账号在浏览器确认授权，领取 B 的默认 Key；AI 费用、余额和记录归 B。软件使用权仍由 A 的 SDK 登录、设备及权益流程独立校验，不能以有效 AI Key 代替。独立 Skills 可省略 app_key，用 client_name 标明名称。`connect()` 返回 API Key 客户端，`authorize()` 返回包含 `api_key` 的授权结果，供宿主写入安全存储；两者都不会自动保存密钥。默认 Key 是通用用户凭证，多个应用可能共用，重置或停用会影响已接入应用。

`connect/authorize` 是阻塞等待方法，GUI 放在后台线程；需要取消或已有事件循环时用 `start()` / `poll(device_code)` 自行调度。只打开返回的 `verification_url`，按返回的 `interval`（至少 3 秒）轮询，最多等待 `expires_in`（默认 600 秒）。`pending` 等待，`denied/consumed` 停止，过期 HTTP 410 停止；429 后放慢查询。授权只能领取一次，领取响应丢失时重新发起授权，不自动重复领取。`device_code` 只放 JSON 请求体，不发到浏览器、URL 或日志。

### 分站来源（0.5.3）

0.5.3 增加可选 `site_code`。软件已有授权登录/校验结果 `license_session` 时：

```python
authorization = QilingAuthorizationClient(
    os.environ["QILING_API_URL"],
    app_key=os.environ["QILING_APP_KEY"],
    site_code=license_session.get("site", {}).get("code", "platform"),
)
client = authorization.connect()
```

平台从有效分站已登记域名生成确认页URL（包括已登记的自定义域名），软件只打开返回的 `verification_url`，不要硬编码主站或自行拼URL。省略/空字符串/`platform` 保持旧主站流程；不存在或停用分站返回404，分站域名无效返回409。来源只影响确认页品牌和新用户注册入口；不会切换已登录B的账号/站点，API Key、调用余额和扣费归B，A的软件授权不变。模型接口仍用原配置地址，不因分站切换。需使用已支持分站来源的器灵平台接口；v0.5.2及更早版本不支持此参数。

`site_code` 取软件授权响应的 `site.code`，不根据 AI 付款账号、浏览器当前域名或软件 slug 推导。404/409 应提示用户联系分站管理员，SDK 不自动改用主站重试。客户端不提交任意 URL、Host 或 redirect_uri 作为授权目的地；该来源字段不是权限凭证，也不是模型 Base URL。

无自动浏览器环境可用 `open_browser=False, on_authorization_url=show_link` 展示链接，`timeout` 限制等待时间。宿主仍需在退出或切换账号时清理自己的密钥副本。

## 从 0.2.x 升级

旧 `QilingAiClient.ai_chat/ai_image/ai_translate` 及对应的 SDK token AI 入口已移除。文本和图片改用 `QilingOpenClient.chat/image`，传用户 API Key 和模型，文本/图片业务请求号可选；翻译可按当前文本模型文档构造对话请求。软件授权登录、设备和普通次数扣减继续保留。

SDK Bearer 的视频接口按当前公开文档提供：`ai_models()`、`ai_estimate(kind, **request)`、`ai_video(prompt=None, *, model, request_id, content=None, ...)`、`ai_task(task_id)`、`ai_cancel_video(task_id)`、`ai_bills(page=1, page_size=20)`。先登录或校验恢复授权上下文；视频同样按调用余额结算，不扣普通次数。该 SDK Bearer 接口仍要求 request_id，支持与开放视频相同的 content、ratio、generate_audio、return_last_frame、参考音频和首尾帧参数。文本和图片使用上面的 API Key 客户端。

## 上架前先调试

SDK 不预设生产域名，初始化时必须显式传入 `base_url`。以下示例通过 `QILING_API_URL` 读取你已确认的 API 根地址，不附加 `/api/v1`；官网链接不代表 API 地址。

保存软件及套餐后，在开发者后台“我的软件 → 开发调试”生成测试 App Key 和测试授权码。软件无需先上架。测试访问窗口为 7 天，支持重置和停用；调试权限不包含付款或真实 AI。

```python
import os
from qiling_ai_sdk import QilingAiClient

client = QilingAiClient(os.environ["QILING_API_URL"])
app_key = os.environ["QILING_TEST_APP_KEY"]
license_key = os.environ["QILING_TEST_LICENSE_KEY"]
bootstrap = client.bootstrap(app_key, test_license_key=license_key)
session = client.license_login(app_key, license_key)
current = client.license_check(app_key)
rights = {item["feature_code"]: item for item in current["entitlements"]}
allowed = current["valid"] and rights.get("default", {}).get("valid", False)
```

`app_key` 使用平台返回的实际值，不是软件英文标识或软件 ID。校验接口 200 不代表授权有效，必须检查整体和实际功能权益。读取到期时间时结合 is_perpetual/pending_activation，不要把 null 一律当永久。

可运行 `examples/quickstart.py` 完成最小测试。设置 `QILING_API_URL`、`QILING_TEST_APP_KEY`、`QILING_TEST_LICENSE_KEY` 后运行；默认不扣额度、不打印凭据。加 `--consume` 才扣一次测试额度，`--feature` 选择具体权益标识。

```sh
python examples/quickstart.py
python examples/quickstart.py --consume --feature default
```

应用提供 Python SDK 后不需要自行申请微信公众号或把平台管理密钥放进客户端。

## 从 0.1.x 升级

部署新会话后端并升级 SDK 后，必须重新执行一次 `license_login`。清除旧的长期 token 缓存，重新取得短期访问凭证和刷新凭证；有效软件授权本身无需重新购买。

服务端返回 `sdk_token`、`refresh_token`、`expires_in` 等字段。访问期限由服务端决定，刷新会话不会延长软件授权、增加额度或代替续费。

## 初始化与登录

```python
import os
from qiling_ai_sdk import QilingAiClient

client = QilingAiClient(base_url=os.environ["QILING_API_URL"])
bootstrap = client.bootstrap(app_key="qi-tui-desktop", site_code="platform")
session = client.license_login(app_key="qi-tui-desktop", license_key="QLIC-xxxx")

credentials = {
    "token": client.get_token(),
    "refresh_token": client.get_refresh_token(),
}
```

应用标识应替换为平台登记值，授权码来自用户输入。默认 `create_desktop_device` 会在用户目录保存随机设备 ID；它不保存登录凭证。也可以传入 `device_provider`，但每次启动必须复用稳定的设备 ID。

## 保存与恢复会话

SDK 默认只在内存保管凭证，不负责持久化。应用应将两项凭据一起保存在系统凭据库或自己的受保护服务端存储中；不要写入普通配置文件、日志、URL或随应用发布的 `.env`。

每次登录、手动刷新，以及可能自动刷新的请求完成后，应重新调用 `get_token()` 和 `get_refresh_token()` 更新宿主安全存储，不能一直保存首次登录的旧快照。

安全存储返回的 `saved` 对象可按以下方式恢复。参数名使用 **snake_case** 的 `refresh_token`：

```python
import os

def restore_client(saved, device_provider=None):
    restored = QilingAiClient(
        base_url=os.environ["QILING_API_URL"],
        token=saved["token"],
        refresh_token=saved["refresh_token"],
        device_provider=device_provider,
    )
    session = restored.license_check(app_key="qi-tui-desktop")
    return restored, session
```

恢复后必须先 `license_check`，重新取得授权、分站和产品缓存，再调用续费或 AI 等依赖授权信息的方法。也可用 `client.set_token(token, refresh_token)` 更新现有实例；该方法会清空授权缓存。不要跨用户共享同一个已登录客户端实例。

## 刷新、错误与退出

受保护请求遇到 HTTP 401 且存在刷新凭证时，SDK 会刷新并仅重试原请求一次。同一实例用锁协调并发刷新，已由其他请求更新的 token 会被复用。403、额度不足及其他业务错误不会触发无限刷新。

```python
client.refresh_session()
credentials = {
    "token": client.get_token(),
    "refresh_token": client.get_refresh_token(),
}
```

`refresh_session()` 返回服务端刷新结果，同时更新客户端凭证；它不会初始化缺失的授权缓存。错误类型为 `QilingAiError`，有 `status` 和 `detail`。刷新凭证失效或已撤销时，需要重新授权码登录；`SESSION_CHANGED` 表示旧会话请求已失效，不应据此覆盖新会话。

```python
client.logout()
```

`logout()` 请求服务端撤销当前会话，并在 `finally` 清空 SDK 内存凭证和授权缓存。宿主仍须在自己的退出流程 `finally` 中删除安全存储副本。请求失败时不能声称服务端撤销成功；SDK 的本地清理不会自动删除外部存储。

## 商品、套餐与续费

```python
store = client.get_storefront(category="AI 视频", keyword="剪辑")
current = client.license_check(app_key="qi-tui-desktop")
plans = current["product"]["plans"]
if plans:
    payment = client.create_renewal_payment(plan_code=plans[0]["code"])
    # 将 payment["code_url"] 渲染为微信支付二维码。
    status = client.get_payment_status(payment["order_no"])
```

授权会话仅支持续费/升级。新购应引导用户打开产品的 `detail_url`，到主站或分站前台完成。`create_payment` 保留兼容入口，但授权会话调用其 `new_license` 流程会被平台拒绝。

商品含名称、简介、详情、图片、轮播图、交付地址、套餐和分站价格。有授权缓存时，`get_storefront` 优先使用授权所属分站；还支持 `site_code`、`app_key`、`category`、`keyword`。

使用套餐时须读取 `quota`、`quota_mode`、`ai_enabled`、设备与账号限制。多模块工具依据响应中的 `entitlements`，按 `feature_code`、`valid` 控制功能。`license.is_free` 标识免费授权；免费升级付费仍走续费接口，升级后的有效期、额度与权益以重新 `license_check` 的结果为准。


### 未上架软件调试

在开发者后台「我的软件 → 开发调试」按草稿套餐生成测试 App Key 和测试授权码，即可调用现有授权登录、校验与额度扣减方法。初始化和套餐查询增加可选测试授权码参数，通过请求头发送；完整用法与隔离规则见 [在线开发文档](https://867fas1f7s.apifox.cn/)。测试窗口为 7 天，重置会撤销旧会话，正式上架后使用生产 App Key。


## 开发与验证

```sh
python -m pip install openai httpx  # 仅官方 SDK 兼容测试需要。
python -m unittest discover -s tests -v
python examples/quickstart.py --help
```

测试使用模拟 HTTP 响应，不创建真实订单、不付款、不调用真实 AI。真实授权联调使用自己在开发者后台生成的测试凭据。

## 许可证

MIT，见 [LICENSE](LICENSE)。


## 模型能力与官方 SDK 桥接

本版保留软件登录、会话、套餐及去AI原文换行处理。普通JSON调用不新增第三方依赖；流式与multipart图片编辑可在Python3.10+安装可选桥接：

```sh
python -m pip install "qiling-ai-sdk[openai] @ git+https://github.com/qilingAI/qiling-sdk-python.git@v0.5.4"
```

```python
import os
from qiling_ai_sdk import QilingOpenClient

client = QilingOpenClient(os.environ["QILING_BASE_URL"], os.environ["QILING_API_KEY"])
with client.openai() as models:
    # 桥接复用同一用户Key、Base URL和可选App Key，默认禁止自动重试。
    for chunk in models.chat.completions.create(
        model=os.environ["QILING_MODEL"],
        messages=[{"role":"user","content":"你好"}], max_tokens=4096,
        stream=True, stream_options={"include_usage":True},
    ):
        if chunk.choices:
            print(chunk.choices[0].delta.content or "", end="")
```

工具使用标准tools函数定义和tool_choice，可配parallel_tool_calls。模型返回tool_calls时content允许为空；由软件校验并执行工具，再用tool_call_id回传结果、再次调用模型。保留原assistant消息（包括供应商要求的reasoning_content），每轮独立计费。视觉消息使用user.content中的text/image_url块，音频使用input_audio，视频理解使用video_url；response_format支持json_object和json_schema。对应能力未开启时平台会在调用供应商前拒绝。

图片编辑使用`with client.openai() as models:`后调用`models.images.edit(model=..., prompt=..., image=open_file)`；图片流式使用`models.images.generate(..., stream=True)`。本SDK不提供单独临时媒体托管。

```python
# 视频使用器灵异步任务协议，content与prompt/便捷参考字段二选一。
video = client.video(
    model=os.environ["QILING_VIDEO_MODEL"],
    content=[
        {"type":"text","text":"参考图片与音频生成视频"},
        {"type":"image_url","image_url":{"url":"https://example.com/替换为图片.png"},"role":"reference_image"},
        {"type":"audio_url","audio_url":{"url":"https://example.com/替换为音频.mp3"},"role":"reference_audio"},
    ], ratio="9:16", generate_audio=True, return_last_frame=True,
    idempotency_key="保存并复用的唯一业务请求号",
)
print(client.model_call(video["id"]))
```

视频支持HTTPS/Data URI参考图/视频/音频、first_frame/last_frame、ratio、generate_audio、return_last_frame；查询和取消继续使用model_call/cancel_video。成功读取data.video_url和所请求且上游返回的data.last_frame_url，计费在billing。不能直接当作官方OpenAI Videos API或Seedance官方任务路径使用。reference_seconds 及额度预估只用于费用估算，不预扣或占用余额，最后按上游真实用量结算；断流、用量缺失或未知结果只核对原任务，不新建请求重试。

最新动态模型契约：已确认平台根地址下的 `/api/v1/open/model-docs` 和 `/api/v1/public/developer-openapi.json`；静态参考见 [Apifox 索引](https://867fas1f7s.apifox.cn/llms.txt)。接入时先读该模型能力与Schema，不能靠别名推断权限。当前仅GitHub源码/Tag发布，不发布公共PyPI包。

## 0.5.1 更新

补齐 SDK Bearer 视频接口的多模态 content、参考音频、首尾帧和音频生成参数。`QilingOpenClient.image` 是普通 JSON 调用；`stream=True` 会在发请求前提示使用官方 SDK 或 `client.openai()` 桥接，避免将 SSE 当作 JSON。图片编辑及图片流式继续沿用官方 `images.edit/generate`，不新增上传协议。

工具、结构化输出、音视频理解、图片编辑/流式和视频素材能力均取决于所选模型的后台配置及供应商支持。先核对动态文档，不把能力列表当作每个模型均已支持的承诺。

## 0.5.2：思考模式、账户与计费

模型目录 `data[].qiling.config` 新增 `supports_thinking`、`thinking_modes`，支持时 capabilities 包含 thinking；动态模型文档的 `request_schema.properties.thinking` 给出允许的 type。更新缓存后再展示思考模式控制，不能仅凭旧缓存或模型别名推断支持。后台显式关闭优先，能力未开放时不要发送该参数。

```python
# 仅在所选模型声明支持 disabled 时使用。
from qiling_ai_sdk import QilingOpenClient

client = QilingOpenClient(os.environ["QILING_BASE_URL"], os.environ["QILING_API_KEY"])
result = client.chat(
    [{"role": "user", "content": "你好"}],
    model=selected_model,
    thinking={"type": "disabled"},
)
```

官方 OpenAI SDK 在 `chat.completions.create` 中使用 `extra_body={"thinking":{"type":"disabled"}}`；线上 JSON 是顶层 thinking，不能嵌套 extra_body。开启时用 enabled。不传参数沿用供应商默认，并不等于关闭；界面应保存用户选择，没有用户选择且模型支持时可显式选择 disabled。CLI 示例新增 `--thinking enabled|disabled`，默认不传参数。reasoning_effort 是另一种控制，不能替代 thinking 开关。

软件登录账号和 AI 付费账号可以不同；切换 AI Key 只切换 AI 账户，不覆盖软件 SDK 会话。软件来源头检查软件状态和 AI 配置，软件使用权仍独立校验。模型消费不再预留资金，可信实际用量确认后扣款；不明结果保留原任务待核对，核对前不扣费或占用余额，不作为零费成功。


### AI 快捷授权入口（0.5.4）

现有 `/api/v1/sdk/license/login` 和 `/api/v1/sdk/license/check` 返回 `product.ai_quick_authorization_enabled`，值为 JSON 布尔值，默认 `true`。按授权所属站点读取该软件的开关：主站和各分站独立，基础分站也可设置。管理员赠送试用、多模块及开发测试授权复用相同返回位置。后台保存后，软件下次登录或校验即可拿到新值。

客户端使用这个值决定是否展示 AI 快捷授权入口；为兼容旧平台，缺失字段可按 `true` 处理，不能用 `value || true`（会覆盖显式 `false`）。这只是客户端入口设置，不替代套餐 `ai_enabled`、授权有效性、用户确认和实际调用权限；不会撤销已经授权的 API Key。未新增独立查询接口或修改调用扣费规则。

Python：`show_ai_quick_auth = session.get("product", {}).get("ai_quick_authorization_enabled", True)`

TypeScript：`const showAiQuickAuth = session.product.ai_quick_authorization_enabled ?? true;`
