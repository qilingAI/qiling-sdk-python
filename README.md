# qiling-ai-sdk 0.2.0

器灵官方 Python SDK，支持授权码登录、分站品牌、套餐权益、设备绑定、额度扣减、AI 调用和微信 Native 续费。支持 Python 3.9+，仅使用标准库，无运行时第三方依赖。

[在线开发文档](https://867fas1f7s.apifox.cn/) · [AI 文档索引](https://867fas1f7s.apifox.cn/llms.txt) · [配套接入 Skills](https://github.com/qilingAI/qiling-skills)

这是从器灵平台已验证的 SDK 拆出的独立仓库，与平台版本 54fcc1f 的接口兼容。

## 安装

从官方仓库安装固定版本：

```sh
python -m pip install "git+https://github.com/qilingAI/qiling-sdk-python.git@v0.2.0"
```

或者克隆源码后安装：

```sh
git clone https://github.com/qilingAI/qiling-sdk-python.git
cd qiling-sdk-python
python -m pip install .
```

包名为 `qiling-ai-sdk`，导入名为 `qiling_ai_sdk`；目前未发布到公共 PyPI，不要把同名来源不明的包当官方 SDK。

## 上架前先调试

保存软件及套餐后，在开发者后台“我的软件 → 开发调试”生成测试 App Key 和测试授权码。软件无需先上架。测试访问窗口为 7 天，支持重置和停用；调试权限不包含付款或真实 AI。

```python
import os
from qiling_ai_sdk import QilingAiClient

client = QilingAiClient("https://ql.xiazq.com")
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
from qiling_ai_sdk import QilingAiClient

client = QilingAiClient(base_url="https://ql.xiazq.com")
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
def restore_client(saved, device_provider=None):
    restored = QilingAiClient(
        base_url="https://ql.xiazq.com",
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
