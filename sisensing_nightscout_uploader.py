#!/usr/bin/env python3
"""
硅基动感亲友分享 -> Nightscout 上传脚本
通过硅基 SIJOY 小程序的亲友分享 API 拉取血糖数据，上传到 Nightscout
自动选择有最新数据的设备，换传感器后无需手动修改 deviceId
"""

import requests
import time
import json
import sys
import os
from datetime import datetime, timezone

# ============ 配置（支持环境变量） ============
SI_API = os.environ.get("SI_API", "https://cxm-api.sisensing.com/cxm-mini-program-share/follow/relation/data/details-v2")
SI_PARAMS = {
    "appCode": os.environ.get("SI_APP_CODE", "SIJOY_HEALTH_APP"),
    "followRelationId": os.environ.get("SI_FOLLOW_RELATION_ID", "2088455721451631438"),
    "deviceId": os.environ.get("SI_DEVICE_ID", "2095153918479945148"),
}
SI_HEADERS = {
    "app_code": os.environ.get("SI_APP_CODE_HEADER", "SHARE_MINI_PROGRAM"),
    "authorization": "Bearer " + os.environ.get("SI_AUTH_TOKEN", "c3217d8f-e448-4a6b-88e9-75d2e22f3247"),
    "timezone": os.environ.get("SI_TIMEZONE", "Asia/Shanghai"),
    "xweb_xhr": "1",
    "user-agent": os.environ.get("SI_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781 NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF XWEB/25510"),
    "content-type": "application/json",
    "sib-agent": os.environ.get("SI_SIB_AGENT", "SHARE_MINI_PROGRAM&01.01.00.00&Windows 11 x64&NULL&microsoft"),
    "accept": "*/*",
    "referer": os.environ.get("SI_REFERER", "https://servicewechat.com/wx48ef5b0c9175e11b/10/page-frame.html"),
    "accept-language": "zh-CN,zh;q=0.9",
}

NS_URL = os.environ.get("NS_URL", "https://9FC3BAB952CCC1A8.abwsz.com")
# API-SECRET = 网站登录密码的 SHA1 哈希
NS_API_SECRET = os.environ.get("NS_API_SECRET", "1160a3a804ed9b811866fa081170667e267c2908")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))  # 秒，默认30秒


def fetch_glucose():
    """从硅基 API 拉取血糖数据，自动选择有最新数据的设备"""
    try:
        resp = requests.get(SI_API, params=SI_PARAMS, headers=SI_HEADERS, timeout=30)
        data = resp.json()
        if data.get("code") != 200:
            print(f"[ERROR] 硅基 API 返回错误: code={data.get('code')}, msg={data.get('msg')}")
            return [], None

        device_info = data["data"].get("deviceInfo", {})
        latest_value = device_info.get("latestValue")
        latest_time = device_info.get("latestTime")

        # 自动选择有最新数据的设备（换传感器后自动切换，无需手动改deviceId）
        all_devices = data["data"].get("deviceGlucoseInfos", [])
        best_device = None
        best_latest_time = 0
        for item in all_devices:
            glucose_list = item.get("glucoseInfos", [])
            if glucose_list:
                device_latest = max(r["t"] for r in glucose_list)
                if device_latest > best_latest_time:
                    best_latest_time = device_latest
                    best_device = item

        if best_device:
            glucose_infos = best_device.get("glucoseInfos", [])
            print(f"[INFO] 自动选择设备: {best_device['deviceId']} (最新数据时间: {best_latest_time})")
        else:
            glucose_infos = []
            print("[WARN] 没有找到有数据的设备")

        return glucose_infos, {"latestValue": latest_value, "latestTime": latest_time}
    except Exception as e:
        print(f"[ERROR] 拉取硅基数据失败: {e}")
        return [], None


def calc_direction(readings, idx):
    """根据最近几个点计算血糖趋势方向"""
    if idx < 2:
        return "Flat"

    # 取最近15分钟（3个点，每5分钟一个）计算变化率
    rates = []
    for j in range(max(0, idx - 3), idx):
        if j + 1 < len(readings):
            dt = (readings[j + 1]["t"] - readings[j]["t"]) / 1000 / 60  # 分钟
            if dt > 0:
                dv = (float(readings[j + 1]["v"]) - float(readings[j]["v"])) * 18  # mmol/L -> mg/dL
                rates.append(dv / dt)  # mg/dL per minute

    if not rates:
        return "Flat"

    avg_rate = sum(rates) / len(rates)

    if avg_rate > 3:
        return "DoubleUp"
    elif avg_rate > 2:
        return "SingleUp"
    elif avg_rate > 1:
        return "FortyFiveUp"
    elif avg_rate > -1:
        return "Flat"
    elif avg_rate > -2:
        return "FortyFiveDown"
    elif avg_rate > -3:
        return "SingleDown"
    else:
        return "DoubleDown"


def to_ns_entries(readings):
    """转换为 Nightscout entries 格式"""
    entries = []
    for i, r in enumerate(readings):
        try:
            mmol = float(r["v"])
            mgdl = round(mmol * 18)  # mmol/L -> mg/dL
            ts = r["t"]
            direction = calc_direction(readings, i)
            date_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

            entries.append({
                "type": "sgv",
                "sgv": mgdl,
                "date": ts,
                "dateString": date_str,
                "direction": direction,
                "device": "sisensing-share",
                "filtered": 0,
                "unfiltered": 0,
                "noise": 0,
                "rssi": 100,
            })
        except Exception as e:
            print(f"[WARN] 跳过异常数据点: {r}, error: {e}")
    return entries


def ns_headers():
    return {
        "API-SECRET": NS_API_SECRET,
        "Content-Type": "application/json",
    }


def upload_to_ns(entries):
    """上传到 Nightscout"""
    if not entries:
        return 0

    url = f"{NS_URL}/api/v1/entries"
    try:
        resp = requests.post(url, json=entries, headers=ns_headers(), timeout=30)
        if resp.status_code in (200, 201):
            return len(entries)
        else:
            print(f"[ERROR] Nightscout 上传失败: status={resp.status_code}, body={resp.text[:500]}")
            return 0
    except Exception as e:
        print(f"[ERROR] Nightscout 上传异常: {e}")
        return 0


def verify_ns():
    """验证 Nightscout 连接"""
    try:
        url = f"{NS_URL}/api/v1/entries.json?count=1"
        resp = requests.get(url, headers={"API-SECRET": NS_API_SECRET}, timeout=15)
        print(f"[INFO] Nightscout 连接测试: status={resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if data:
                latest = data[0]
                mmol = latest.get("sgv", 0) / 18
                print(f"[INFO] Nightscout 最新数据: {latest.get('sgv')} mg/dL ({mmol:.1f} mmol/L), date={latest.get('dateString')}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR] Nightscout 连接失败: {e}")
        return False


def run_once():
    """执行一次拉取并上传"""
    readings, device_info = fetch_glucose()
    if not readings:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 未拉取到数据")
        return 0

    entries = to_ns_entries(readings)
    uploaded = upload_to_ns(entries)

    latest_mmol = float(readings[-1]["v"]) if readings else 0
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 拉取{len(readings)}条, 上传{uploaded}条, 最新值: {latest_mmol} mmol/L")
    return uploaded


def run_daemon():
    """持续运行模式：每 POLL_INTERVAL 秒拉取一次"""
    print("=" * 60)
    print("硅基动感亲友分享 -> Nightscout 上传器 (持续运行模式)")
    print(f"轮询间隔: {POLL_INTERVAL}秒 ({POLL_INTERVAL//60}分钟)")
    print("=" * 60)

    if not verify_ns():
        print("[FATAL] Nightscout 连接失败")
        sys.exit(1)

    print(f"\n[启动] 开始持续上传，按 Ctrl+C 停止\n")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[ERROR] 循环异常: {e}")
        time.sleep(POLL_INTERVAL)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        run_daemon()
    else:
        # 单次运行模式
        print("=" * 60)
        print("硅基动感亲友分享 -> Nightscout 上传器 (单次模式)")
        print("=" * 60)

        print("\n[1/3] 验证 Nightscout 连接...")
        if not verify_ns():
            print("[FATAL] Nightscout 连接失败")
            sys.exit(1)

        print("\n[2/3] 从硅基 API 拉取血糖数据...")
        readings, device_info = fetch_glucose()
        print(f"      拉取到 {len(readings)} 条血糖记录")
        if device_info:
            print(f"      最新值: {device_info['latestValue']} mmol/L")
            if readings:
                print(f"      数据范围: {readings[0]['v']} -> {readings[-1]['v']} mmol/L")

        if not readings:
            print("[WARN] 没有拉取到血糖数据")
            sys.exit(1)

        print("\n[3/3] 转换并上传到 Nightscout...")
        entries = to_ns_entries(readings)
        uploaded = upload_to_ns(entries)
        print(f"      成功上传 {uploaded} 条数据")

        print("\n[验证] 从 Nightscout 读取最新5条数据...")
        try:
            url = f"{NS_URL}/api/v1/entries.json?count=5"
            resp = requests.get(url, headers={"API-SECRET": NS_API_SECRET}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for entry in data:
                    mmol = entry.get("sgv", 0) / 18
                    print(f"      {entry.get('dateString')} | {entry.get('sgv')} mg/dL ({mmol:.1f} mmol/L) | {entry.get('direction')} | {entry.get('device')}")
        except Exception as e:
            print(f"[ERROR] 验证失败: {e}")

        print("\n" + "=" * 60)
        print("单次上传完成！加 --daemon 参数可持续运行")
        print("=" * 60)


if __name__ == "__main__":
    main()
