# qiling-ai-sdk 0.3.0

器灵官方 Python SDK，支持软件授权、套餐权益、设备与额度管理、API Key 快速授权、开放模型调用及任务查询。支持 Python 3.9+，仅使用标准库，无运行时第三方依赖。

[官网](https://toolsoul.daniu7.cn) · [在线开发文档](https://867fas1f7s.apifox.cn/) · [AI 文档索引](https://867fas1f7s.apifox.cn/llms.txt) · [配套接入 Skills](https://github.com/qilingAI/qiling-skills)

接口已按 2026-10-15 的公开 API 文档核对。官网链接用于访问网站；API 根地址由接入配置明确提供，SDK 不预设生产域名。

## 安装

从官方仓库安装固定版本：

```sh
python -m pip install "git+https://github.com/qilingAI/qiling-sdk-python.git@v0.3.0"
```

或者克隆源码后安装：

```sh
git clone https://github.com/qilingAI/qiling-sdk-python.git
cd qiling-sdk-python
python -m pip install .
```

包名为 `qiling-ai-sdk`，导入名为 `qiling_ai_sdk`；目前未发布到公共 PyPI，不要把同名来源不明的包当官方 SDK。

## 选择客户端

| 客户端 | 凭证与用途 |
|---|---|
| `QilingAiClient` | 授权码登录取得 SDK 会话，用于软件权益、设备、普通额度、续费及公开文档保留的 SDK AI 视频接口 |
| `QilingOpenClient` | 用户 API Key，用于文本、图片、视频、通用工具、调用余额和使用记录 |
| `QilingAuthorizationClient` | 打开浏览器让用户确认，再一次性领取 API Key；不需要本地回调服务 |

账号 token、SDK token 和用户 API Key 用途不同，不能互相替换。软件调用开放模型时传 `app_key`，服务端校验正式软件授权和套餐 AI 开关；独立工具直接调用可省略。App Key 使用平台返回值，不根据软件 ID 或 slug 自行推导。

## 开放模型与工具

已有 API Key 时，从环境或应用的安全存储读取：

```python
import os
from qiling_ai_sdk import QilingOpenClient

client = QilingOpenClient(
    os.environ["QILING_API_URL"],
    os.environ["QILING_API_KEY"],
    app_key=os.environ.get("QILING_APP_KEY"),  # 软件接入必填；独立调用可省略。
)
models = client.models()
docs = client.model_docs()
balance = client.balance()
```

先查询 `models()` 和 `model_docs()`，从返回值选择模型，按每项 `request_schema`、`limits` 和 `pricing` 构造请求。返回的示例是说明数据，不应自动执行。不要假定有默认模型、固定模型清单、价格或尺寸。

以下调用会消耗用户调用余额。`model` 和 `request_id` 都是必填参数；业务请求号在首次提交前生成并保存，同一业务重试复用，不同内容不能共用。

```python
request_id = saved_business_request_id  # 来自应用已持久化的业务请求。
result = client.chat(
    [{"role": "user", "content": "你好"}],
    model=selected_model,
    request_id=request_id,
    max_tokens=1000,
)
call_id = result["id"]  # 保存后用 model_call(call_id) 查询原调用。
```

| 方法 | 用途 |
|---|---|
| `chat(messages, *, model, request_id, max_tokens=None, temperature=None)` | 非流式文本调用 |
| `image(prompt, *, model, request_id, n=1, size=None, reference_images=None, layer_decomposition=False)` | 图片生成、参考图与图层拆分 |
| `video(prompt, *, model, request_id, duration=5, resolution="720p", reference_images=None, reference_video=None, reference_seconds=0)` | 创建视频任务 |
| `estimate(kind, request)` | 以完整调用参数预估费用，kind 为 text/image/video；不调用上游、不冻结余额 |
| `model_call(call_id)` / `cancel_video(call_id)` | 查询原模型任务 / 请求取消视频 |
| `balance()` / `usage(days=30, endpoint="")` / `logs(limit=50, offset=0, days=30, endpoint="")` | 调用余额、当前 Key 统计与记录 |
| `endpoints()` / `submit_task(endpoint, input="", options=None)` / `task(task_id)` | 通用工具目录、提交与结果查询 |
| `remove_ai(text)` | 提交去 AI 任务，保存返回的 task_id 后用 task 查询 |

`usage`、`logs` 的参数，以及 `submit_task` 的 `options` 为关键字参数。通用工具的 task_id 和模型调用的 id 使用不同查询接口。

去 AI 改文依赖原文段落结构。`remove_ai(text)` 和 `submit_task("remove_ai", input=text)` 会原样提交正文，保留真实换行与空行。调用前不要把段落用空格合并、清洗空白，或手动将换行替换成字面量反斜杠加 n；JSON 序列化由 SDK 完成。需要保留文件原始换行格式时可用 `Path(path).read_bytes().decode("utf-8-sig")` 读取正文。

模型生成前冻结预计费用，完成后按实际用量和请求开始时的价格快照结算；不要再调用 `consume_quota` 为模型重复扣次。价格已经包含倍率，不再手动乘算。费用为十进制字符串，需计算时使用 `decimal.Decimal`；`billing.fee=null` 表示未完成或待核对，不能视为免费。

`succeeded` 才表示生成完成。`queued/running/cancel_requested` 继续查询同一 id；`unknown/review` 等待核对，不重新生成。取消请求被接受不代表取消或退款已完成。网络结果不明时 SDK 不自动重发生成请求，保留业务请求号并查询原任务。HTTP 402 表示余额不足，401 需要处理 API Key，不能用 SDK refresh_token 刷新 API Key。

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

软件传入平台登记的正式 App Key；独立 Skills 调用可省略 `app_key`，用 `client_name` 标明名称。`connect()` 返回 API Key 客户端，`authorize()` 返回包含 `api_key` 的授权结果，供宿主写入安全存储；两者都不会自动保存密钥。默认 Key 是通用用户凭证，多个应用可能共用，重置或停用会影响已接入应用。

`connect/authorize` 是阻塞等待方法，GUI 放在后台线程；需要取消或已有事件循环时用 `start()` / `poll(device_code)` 自行调度。只打开返回的 `verification_url`，按返回的 `interval`（至少 3 秒）轮询，最多等待 `expires_in`（默认 600 秒）。`pending` 等待，`denied/consumed` 停止，过期 HTTP 410 停止；429 后放慢查询。授权只能领取一次，领取响应丢失时重新发起授权，不自动重复领取。`device_code` 只放 JSON 请求体，不发到浏览器、URL 或日志。

无自动浏览器环境可用 `open_browser=False, on_authorization_url=show_link` 展示链接，`timeout` 限制等待时间。宿主仍需在退出或切换账号时清理自己的密钥副本。

## 从 0.2.x 升级

旧 `QilingAiClient.ai_chat/ai_image/ai_translate` 及对应的 SDK token AI 入口已移除。文本和图片改用 `QilingOpenClient.chat/image`，传用户 API Key、明确模型和业务请求号；翻译可按当前文本模型文档构造对话请求。软件授权登录、设备和普通次数扣减继续保留。

SDK Bearer 的视频接口按当前公开文档提供：`ai_models()`、`ai_estimate(kind, **request)`、`ai_video(prompt, *, model, request_id, ...)`、`ai_task(task_id)`、`ai_cancel_video(task_id)`、`ai_bills(page=1, page_size=20)`。先登录或校验恢复授权上下文；视频同样按调用余额结算，不扣普通次数。文本和图片使用上面的 API Key 客户端。

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
python -m unittest discover -s tests -v
python examples/quickstart.py --help
```

测试使用模拟 HTTP 响应，不创建真实订单、不付款、不调用真实 AI。真实授权联调使用自己在开发者后台生成的测试凭据。

## 许可证

MIT，见 [LICENSE](LICENSE)。
