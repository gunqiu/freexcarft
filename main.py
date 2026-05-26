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
ACTION_ID = os.getenv("FXC_ACTION_ID")
SUPABASE_URL = "https://aeilbxxjgrnnqmtwnesh.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFlaWxieHhqZ3JubnFtdHduZXNoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEzMTY4NjUsImV4cCI6MjA4Njg5Mjg2NX0.ZuGQzVsHX8nnvo1JFoBCOokEjaW-no-QKEe_yco7kUA"

EMAIL = os.getenv("FXC_EMAIL")
PASSWORD = os.getenv("FXC_PASS")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

def send_tg_notification(content):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": content, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=10)
    except: pass

def parse_time(time_str):
    """健壮的时间解析函数"""
    if not time_str: return None
    try:
        # 处理常见格式: 2026-04-01T15:53:16.74+00:00 或 2026-04-01T15:53:16Z
        # 兼容不同长度的毫秒
        clean_ts = re.sub(r'(\.\d+)', lambda m: m.group(0)[:7].ljust(7, '0'), time_str)
        clean_ts = clean_ts.replace('Z', '+00:00')
        return datetime.fromisoformat(clean_ts)
    except Exception as e:
        print(f"⚠️ 解析日期失败 [{time_str}]: {e}")
        # 最后的兜底方案：只取前19位 (YYYY-MM-DDTHH:MM:SS)
        try:
            base_time = time_str.split('.')[0].split('+')[0].replace('Z', '')
            return datetime.strptime(base_time, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except:
            return None

def run_task():
    # 卫语句检查：确保三个核心变量都有值
    if not EMAIL or not PASSWORD or not SERVER_ID or not ACTION_ID:
        print("❌ 错误: 环境变量未设置完整 (检查 EMAIL, PASS, SERVER_ID 或 ACTION_ID)")
        return

    current_ua = random.choice(USER_AGENTS)
    session = requests.Session()
    session.headers.update({"User-Agent": current_ua})

    print(f"📡 正在登录账号: {EMAIL}...")
    login_headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    r_login = session.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", 
                          json={"email": EMAIL, "password": PASSWORD}, headers=login_headers)
    
    if r_login.status_code != 200:
        send_tg_notification(f"❌ <b>续期登录失败</b>\n{r_login.text}")
        return
    
    auth_data = r_login.json()
    access_token = auth_data.get("access_token")
    
    # 构造身份 Cookie
    cookie_dict = {
        "access_token": access_token,
        "refresh_token": auth_data.get("refresh_token"),
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": int(time.time()) + 3600,
        "user": auth_data.get("user")
    }
    cookie_val = f"base64-{base64.b64encode(json.dumps(cookie_dict).encode()).decode()}"
    session.cookies.set("sb-aeilbxxjgrnnqmtwnesh-auth-token", cookie_val, domain="freexcraft.com")

    time.sleep(random.randint(2, 5))
    print(f"🛠️ 正在发送续期 Action...")
    
    action_headers = {
        "accept": "text/x-component",
        "content-type": "text/plain;charset=UTF-8",
        "next-action": ACTION_ID,
        "referer": f"https://freexcraft.com/dashboard/server/{SERVER_ID}"
    }
    r_action = session.post(f"https://freexcraft.com/dashboard/server/{SERVER_ID}", 
                           data=f'["{SERVER_ID}"]', headers=action_headers)

    if r_action.status_code != 200:
        send_tg_notification(f"❌ <b>续期 Action 失败</b>\n状态码: {r_action.status_code}")
        return

    print(f"🎉 续期请求已发送，等待同步...")
    time.sleep(5)

    # 获取结果
    info_headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"}
    r_info = requests.get(f"{SUPABASE_URL}/rest/v1/servers?id=eq.{SERVER_ID}&select=*", headers=info_headers)
    
    if r_info.status_code == 200 and len(r_info.json()) > 0:
        data = r_info.json()[0]
        deadline = parse_time(data.get('renewal_deadline'))
        
        if deadline:
            remaining = deadline - datetime.now(timezone.utc)
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            
            report = (
                f"✅ <b>FreeXCraft 自动续期成功</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🖥 <b>服务器:</b> <code>{data.get('name')}</code>\n"
                f"⏰ <b>剩余寿命:</b> <code>{max(0, hours)}小时 {max(0, minutes)}分钟</code>\n"
                f"📅 <b>过期时间:</b> <code>{(deadline + timedelta(hours=8)).strftime('%m-%d %H:%M')}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚀 <b>状态:</b> 自动守护中"
            )
            send_tg_notification(report)
            print("✅ 任务完成")
        else:
            send_tg_notification("✅ 续期已成功，但过期时间字段解析异常。")
    else:
        send_tg_notification("✅ 续期指令已发送，但未能获取到最新数据。")

if __name__ == "__main__":
    run_task()
