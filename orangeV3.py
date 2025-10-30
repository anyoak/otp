import os, re, time, requests
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import phonenumbers, pycountry
import bot_config as config

active_calls = {}
pending_recordings = {}
os.makedirs(config.DOWNLOAD_FOLDER, exist_ok=True)

# ----- Utilities -----
def country_to_flag(code):
    return "".join(chr(127397+ord(c)) for c in code.upper()) if code else "🏳️"

def detect_country(number):
    try:
        digits = re.sub(r"\D","",number)
        parsed = phonenumbers.parse("+"+digits, None)
        region = phonenumbers.region_code_for_number(parsed)
        country = pycountry.countries.get(alpha_2=region)
        if country: return country.name, country_to_flag(region)
    except: pass
    return "Unknown","🏳️"

def mask_number(number):
    d = re.sub(r"\D","",number)
    return d[:4]+"****"+d[-3:] if len(d)>6 else number

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        res = requests.post(url,json={"chat_id":config.CHAT_ID,"text":text,"parse_mode":"HTML"},timeout=10)
        if res.ok: return res.json().get("result",{}).get("message_id")
    except: pass
    return None

def delete_message(msg_id):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests.post(url,data={"chat_id":config.CHAT_ID,"message_id":msg_id},timeout=5)
    except: pass

def send_voice(voice_path, caption):
    try:
        if os.path.getsize(voice_path)<1000: return False
        url=f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice"
        with open(voice_path,"rb") as f:
            payload={"chat_id":config.CHAT_ID,"caption":caption,"parse_mode":"HTML"}
            files={"voice":f}
            r=requests.post(url,data=payload,files=files,timeout=60)
            return r.status_code==200
    except: return False

# ----- Chrome session for downloads -----
def get_session(driver):
    import requests
    session = requests.Session()
    for c in driver.get_cookies(): session.cookies.set(c['name'],c['value'])
    return session

def construct_url(did,uuid):
    return f"https://www.orangecarrier.com/live/calls/sound?did={did}&uuid={uuid}"

def download_recording(driver,did,uuid,file_path):
    try:
        session=get_session(driver)
        headers={'User-Agent':'Mozilla/5.0','Referer':config.CALL_URL,'Accept':'audio/mpeg'}
        for attempt in range(config.MAX_RETRIES):
            r=session.get(construct_url(did,uuid),headers=headers,timeout=30,stream=True)
            if r.status_code==200 and int(r.headers.get('Content-Length',0))>1000:
                with open(file_path,"wb") as f:
                    for chunk in r.iter_content(8192): f.write(chunk)
                return True
            time.sleep(3)
        return False
    except: return False

# ----- Core -----
def extract_calls(driver):
    global active_calls,pending_recordings
    try:
        table=WebDriverWait(driver,10).until(EC.presence_of_element_located((By.ID,"LiveCalls")))
        rows=table.find_elements(By.TAG_NAME,"tr")
        current_ids=set()
        for r in rows:
            try:
                row_id=r.get_attribute("id")
                if not row_id: continue
                cells=r.find_elements(By.TAG_NAME,"td")
                if len(cells)<5: continue
                number=re.sub(r"\D","",cells[1].text.strip())
                if not number: continue
                current_ids.add(row_id)
                if row_id not in active_calls:
                    country,flag=detect_country(number)
                    masked=mask_number(number)
                    msg_id=send_message(f"📞 New call from {flag} {masked}")
                    active_calls[row_id]={"msg_id":msg_id,"flag":flag,"country":country,"masked":masked,"did_number":number,"detected_at":datetime.now(),"last_seen":datetime.now()}
                else: active_calls[row_id]["last_seen"]=datetime.now()
            except StaleElementReferenceException: continue
        now=datetime.now()
        for cid,info in list(active_calls.items()):
            if cid not in current_ids or (now-info["last_seen"]).total_seconds()>15:
                pending_recordings[cid]={**info,"completed_at":now,"checks":0,"last_check":now}
                if info["msg_id"]: delete_message(info["msg_id"])
                send_message(f"{info['flag']} {info['masked']} — Recording processing...")
                del active_calls[cid]
    except TimeoutException:
        print("[⏱️] No active calls found")

def process_recordings(driver):
    global pending_recordings
    now=datetime.now()
    for cid,info in list(pending_recordings.items()):
        if (now-info["last_check"]).total_seconds()<config.RECORDING_RETRY_DELAY: continue
        info["checks"]+=1
        info["last_check"]=now
        file_path=os.path.join(config.DOWNLOAD_FOLDER,f"call_{info['did_number']}_{now.strftime('%Y%m%d_%H%M%S')}.mp3")
        if download_recording(driver,info['did_number'],cid,file_path):
            caption=f"```🔥 NEW CALL ARRIVED 🔥```\n⏰ {info['detected_at'].strftime('%Y-%m-%d %I:%M:%S %p')}\n{info['flag']} Country: {info['country']}\n📞 Number: {info['masked']}\n```✨ Configure by professor_cry```"
            if send_voice(file_path,caption):
                print(f"[✅] Sent: {file_path}")
            pending_recordings.pop(cid)
        elif info["checks"]>config.MAX_RETRIES:
            send_message(f"❌ Recording not available for {info['flag']} {info['masked']}")
            pending_recordings.pop(cid)

# ----- Browser -----
def wait_login(driver):
    print("➡️ Login manually...")
    try:
        WebDriverWait(driver,600).until(lambda d: not d.current_url.startswith(config.LOGIN_URL))
        return True
    except TimeoutException: return False

def init_driver():
    options=uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    return uc.Chrome(options=options)

# ----- Main -----
def main():
    driver=None
    try:
        driver=init_driver()
        driver.get(config.LOGIN_URL)
        if not wait_login(driver): return
        driver.get(config.CALL_URL)
        WebDriverWait(driver,15).until(EC.presence_of_element_located((By.ID,"LiveCalls")))
        print("[*] Monitoring started...")
        last_check=datetime.now()
        while True:
            extract_calls(driver)
            if (datetime.now()-last_check).total_seconds()>=config.CHECK_INTERVAL:
                process_recordings(driver)
                last_check=datetime.now()
            time.sleep(config.CHECK_INTERVAL)
    except Exception as e: print(f"[💥] Fatal error: {e}")
    finally: 
        if driver: driver.quit()
        print("[*] Monitoring stopped")

if __name__=="__main__": main()
