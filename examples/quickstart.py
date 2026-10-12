"""使用真实测试凭据验证授权接入；默认不扣额度，也不输出任何凭证。"""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description="器灵 SDK 测试授权接入示例。")
    parser.add_argument('--consume', action='store_true', help="明确执行一次测试额度扣减。")
    parser.add_argument('--feature', default='default', help="要验证的功能权益标识。")
    args = parser.parse_args()
    base_url = os.getenv('QILING_API_URL', 'http://127.0.0.1:8000').rstrip('/')
    app_key = os.getenv('QILING_TEST_APP_KEY', '')
    license_key = os.getenv('QILING_TEST_LICENSE_KEY', '')
    if not app_key or not license_key:
        raise SystemExit('请设置 QILING_TEST_APP_KEY 和 QILING_TEST_LICENSE_KEY，不要使用示例占位值。')
    host = urlsplit(base_url).hostname
    if urlsplit(base_url).scheme != 'https' and host not in {'127.0.0.1','localhost','::1'}:
        raise SystemExit('非本机环境必须使用 HTTPS。')
    from qiling_ai_sdk import QilingAiClient, QilingAiError
    client = QilingAiClient(base_url)
    logged_in = False
    try:
        bootstrap = client.bootstrap(app_key, test_license_key=license_key)
        if not bootstrap['product'].get('testing'):
            raise SystemExit('本示例仅用于测试授权，请确认使用测试 App Key。')
        session = client.license_login(app_key, license_key)
        logged_in = True
        checked = client.license_check(app_key)
        if not checked.get('testing') or not checked.get('valid'):
            raise SystemExit('测试授权当前不可用，请检查到期时间与状态。')
        rights = {row['feature_code']:row for row in checked['entitlements']}
        if not rights.get(args.feature, {}).get('valid'):
            raise SystemExit('所选功能权益不可用，请检查 feature_code、期限和额度。')
        print('初始化、授权登录、设备绑定和功能校验成功。')
        if args.consume:
            if checked['license']['quota_total'] is None:
                raise SystemExit('套餐没有额度配置，请不要使用 --consume。')
            result = client.consume_quota(1, feature_code=args.feature)
            print(f"测试扣减成功，剩余额度：{result['remaining']}")
    except QilingAiError as error:
        # 不打印请求对象或 detail，避免不受信任的响应把凭据带入日志。
        raise SystemExit(f'接口请求失败（HTTP {error.status}），请按错误排查文档处理。') from None
    finally:
        if logged_in:
            try:
                client.logout()
            except QilingAiError:
                print('本地会话已清理；服务端退出未确认，请在平台停用该测试授权。')


if __name__ == '__main__':
    main()
