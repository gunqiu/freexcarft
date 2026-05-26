import requests
import os
import json
import base64
import time
import random
import re
from datetime import datetime, timezone, timedelta

# ================= 核心配置 =================

SERVER_ID = os.getenv("FXC_SERVER_ID")
ACTION_ID = os.getenv("FXC_ACTION_ID")  # 可选：没有就跳过旧版续期 Action

SUPABASE_URL = "https://aeilbxxjgrnnqmtwnesh.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFlaWxieHhqZ3JubnFtdHduZXNoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEzMTY4NjUsImV4cCI6MjA4Njg5Mjg2NX0.ZuGQzVsHX8nnvo1JFoBCOokEjaW-no-QKEe_yco7kUA"

EMAIL = os.getenv("FXC_EMAIL")
PASSWORD = os.getenv("FXC_PASS")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def send_tg_notification(content):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": content,
        "parse_mode": "HTML",
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def parse_time(time_str):
    if not time_str:
        return None

    try:
        clean_ts = re.sub(
            r"(\.\d+)",
            lambda m: m.group(0)[:7].ljust(7, "0"),
            time_str,
        )
        clean_ts = clean_ts.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_ts)
    except Exception as e:
        print(f"⚠️ 解析日期失败 [{time_str}]: {e}")

        try:
            base_time = time_str.split(".")[0].split("+")[0].replace("Z", "")
            return datetime.strptime(base_time, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            return None


def query_server_info(access_token):
    info_headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token}",
    }

    return requests.get(
        f"{SUPABASE_URL}/rest/v1/servers?id=eq.{SERVER_ID}&select=*",
        headers=info_headers,
        timeout=20,
    )


def run_task():
    if not EMAIL or not PASSWORD or not SERVER_ID:
        msg = "❌ 错误: 环境变量未设置完整，请检查 FXC_EMAIL、FXC_PASS、FXC_SERVER_ID"
        print(msg)
        send_tg_notification(msg)
        return

    current_ua = random.choice(USER_AGENTS)

    session = requests.Session()
    session.headers.update({"User-Agent": current_ua})

    print(f"📡 正在登录账号: {EMAIL}...")

    login_headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }

    r_login = session.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        json={"email": EMAIL, "password": PASSWORD},
        headers=login_headers,
        timeout=20,
    )

    if r_login.status_code != 200:
        msg = f"❌ <b>FreeXCraft 登录失败</b>\n{r_login.text}"
        print(msg)
        send_tg_notification(msg)
        return

    auth_data = r_login.json()
    access_token = auth_data.get("access_token")

    if not access_token:
        msg = "❌ 登录成功，但没有获取到 access_token"
        print(msg)
        send_tg_notification(msg)
        return

    cookie_dict = {
        "access_token": access_token,
        "refresh_token": auth_data.get("refresh_token"),
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": int(time.time()) + 3600,
        "user": auth_data.get("user"),
    }

    cookie_val = f"base64-{base64.b64encode(json.dumps(cookie_dict).encode()).decode()}"

    session.cookies.set(
        "sb-aeilbxxjgrnnqmtwnesh-auth-token",
        cookie_val,
        domain="freexcraft.com",
    )

    time.sleep(random.randint(2, 5))

    action_status = "未设置 FXC_ACTION_ID，已跳过旧版续期 Action"

    if ACTION_ID:
        print("🛠️ 检测到 FXC_ACTION_ID，正在发送旧版续期 Action...")

        action_headers = {
            "accept": "text/x-component",
            "content-type": "text/plain;charset=UTF-8",
            "next-action": ACTION_ID,
            "referer": f"https://freexcraft.com/dashboard/server/{SERVER_ID}",
        }

        try:
            r_action = session.post(
                f"https://freexcraft.com/dashboard/server/{SERVER_ID}",
                data=f'["{SERVER_ID}"]',
                headers=action_headers,
                timeout=30,
            )

            if r_action.status_code == 200:
                action_status = "旧版续期 Action 已发送"
                print("🎉 旧版续期请求已发送，等待同步...")
                time.sleep(5)
            else:
                action_status = f"旧版续期 Action 失败，状态码 {r_action.status_code}"
                print(f"⚠️ {action_status}")

        except Exception as e:
            action_status = f"旧版续期 Action 请求异常: {e}"
            print(f"⚠️ {action_status}")
    else:
        print("ℹ️ 未设置 FXC_ACTION_ID，跳过旧版续期 Action，仅查询服务器状态")

    r_info = query_server_info(access_token)

    if r_info.status_code == 200 and len(r_info.json()) > 0:
        data = r_info.json()[0]
        deadline = parse_time(data.get("renewal_deadline"))

        if deadline:
            remaining = deadline - datetime.now(timezone.utc)
            total_seconds = max(0, int(remaining.total_seconds()))
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60

            report = (
                f"✅ <b>FreeXCraft 状态检查完成</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>账号:</b> <code>{EMAIL}</code>\n"
                f"🖥 <b>服务器:</b> <code>{data.get('name')}</code>\n"
                f"🆔 <b>服务器ID:</b> <code>{SERVER_ID}</code>\n"
                f"⏰ <b>剩余寿命:</b> <code>{hours}小时 {minutes}分钟</code>\n"
                f"📅 <b>过期时间:</b> <code>{(deadline + timedelta(hours=8)).strftime('%m-%d %H:%M')}</code>\n"
                f"🛠 <b>Action:</b> <code>{action_status}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚀 <b>状态:</b> 自动守护中"
            )

            print(report)
            send_tg_notification(report)
        else:
            msg = (
                f"✅ FreeXCraft 登录成功，服务器信息已获取，但 renewal_deadline 字段解析失败。\n"
                f"Action: {action_status}"
            )
            print(msg)
            send_tg_notification(msg)

    else:
        msg = (
            f"⚠️ FreeXCraft 登录成功，但未能获取服务器数据。\n"
            f"状态码: {r_info.status_code}\n"
            f"返回内容: {r_info.text[:500]}\n"
            f"Action: {action_status}"
        )
        print(msg)
        send_tg_notification(msg)


if __name__ == "__main__":
    run_task()
