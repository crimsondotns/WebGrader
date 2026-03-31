import os
import requests
import time
import gspread
from datetime import datetime
from dotenv import load_dotenv

os.system('') 

def get_timestamp():
    return datetime.now().strftime("%a, %d %b %y %H:%M:%S")

def to_number(val, num_type=float):
    if val is None or val == "":
        return ""
    if isinstance(val, (dict, list)):
        return str(val)
    try:
        return num_type(val)
    except (ValueError, TypeError):
        return str(val)

# --- ฟังก์ชันวิเคราะห์ความเสี่ยง (มีบัตรผ่าน VIP ให้เหรียญระดับโลก) ---
def analyze_risk(history_scams, is_honeypot, is_proxy, is_mintable, slippage_mod, buy_tax, sell_tax, fake_token, trust_list, is_in_cex, is_airdrop_scam, is_blacklisted):
    def safe_float(val):
        try: return float(val) if val != "" else 0.0
        except: return 0.0

    h_scams = safe_float(history_scams)
    honeypot = safe_float(is_honeypot)
    proxy = safe_float(is_proxy)
    mintable = safe_float(is_mintable)
    slip_mod = safe_float(slippage_mod)
    b_tax = safe_float(buy_tax)
    s_tax = safe_float(sell_tax)
    fake = safe_float(fake_token)
    trust = safe_float(trust_list)
    airdrop = safe_float(is_airdrop_scam)
    blacklisted = safe_float(is_blacklisted)
    
    # เช็คว่าเป็นเหรียญใหญ่ที่ลิสต์บน CEX ไหม (ถ้ามีความยาวแปลว่ามีชื่อกระดานเทรด)
    on_cex = True if isinstance(is_in_cex, str) and len(is_in_cex) > 2 else False

    score = 100
    
    # หักคะแนนตามความเสี่ยง
    if honeypot == 1 or fake == 1 or airdrop == 1 or b_tax >= 1 or s_tax >= 1:
        score = 0
    elif h_scams > 0:
        score = 0
    else:
        if proxy == 1: score -= 20
        if mintable == 1: score -= 20
        if slip_mod == 1: score -= 10
        if b_tax > 0.15: score -= 20
        elif b_tax > 0: score -= int(b_tax * 100)
        if s_tax > 0.15: score -= 20
        elif s_tax > 0: score -= int(s_tax * 100)
        if blacklisted == 1: score -= 15
        
    # โบนัส
    if trust == 1: score += 40
    if on_cex: score += 50
    
    # จำกัดคะแนนให้อยู่ใน 0-100
    score = max(0, min(100, int(score)))

    # 👑 กฎพิเศษ: บัตรผ่าน VIP สำหรับเหรียญระดับโลก (Bluechip / Trusted)
    if trust == 1 or on_cex:
        # ต่อให้เป็น Proxy หรือ Mintable ก็ให้ผ่าน เพราะเป็นระบบของโปรเจกต์ใหญ่ที่อัปเกรดได้
        # ยกเว้นว่ามันดันเป็น Honeypot หรือ เหรียญปลอม (Fake) ให้ด่าเหมือนเดิม
        if honeypot == 1 or fake == 1 or b_tax >= 1:
            return "🚩 SCAM (FAKE TRUSTED)", score
        return "💎 BLUECHIP / TRUSTED", score

    # กฎข้อที่ 1: โกงแน่นอน (หนีไปให้ไกล)
    if score == 0 or proxy == 1 or h_scams > 0:
        return "🚩 SCAM / RUG PULL", score
    
    # กฎข้อที่ 2: เสี่ยงสูงมาก (เจ้ามือคุมได้)
    if score < 70 or mintable == 1 or slip_mod == 1 or b_tax > 0.15 or s_tax > 0.15:
        return "⚠️ HIGH RISK", score
    
    # กฎข้อที่ 3: ผ่านเกณฑ์เบื้องต้น
    return "✅ PASS / MONITOR", score
# -------------------------------------------------------------

def fetch_goplus_data(row_data, network, address, session):
    url = f"https://api.gopluslabs.io/api/v1/token_security/{network}?contract_addresses={address}"
    
    max_retries = 6 # จำนวนการลองใหม่กรณีติด Rate Limit
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = session.get(url, timeout=15)
            load_time = time.time() - start_time
            
            if response.status_code == 200:
                json_data = response.json()
                
                if json_data.get("code") == 1 and "result" in json_data:
                    address_key = address.lower()
                    
                    if address_key in json_data["result"]:
                        data_res = json_data["result"][address_key]
                        
                        # ดึงข้อมูลพื้นฐาน
                        token_name = data_res.get("token_name", "")
                        token_sym = data_res.get("token_symbol", "")
                        
                        # Insight Fields
                        history_scams = to_number(data_res.get("honeypot_with_same_creator", ""), int)
                        creator_percent = to_number(data_res.get("creator_percent", ""), float)
                        
                        # Liquidity เอามาจาก Pool แรก
                        dex_list = data_res.get("dex", [])
                        liquidity = ""
                        if dex_list and len(dex_list) > 0:
                            liquidity = to_number(dex_list[0].get("liquidity", ""), float)
                            
                        slippage_mod = to_number(data_res.get("slippage_modifiable", ""), int)
                        is_mintable = to_number(data_res.get("is_mintable", ""), int)
                        cooldown = to_number(data_res.get("trading_cooldown", ""), int)
                        owner_address = data_res.get("owner_address", "")
                        is_honeypot = to_number(data_res.get("is_honeypot", ""), int)
                        is_proxy = to_number(data_res.get("is_proxy", ""), int)
                        buy_tax = to_number(data_res.get("buy_tax", ""), float)
                        sell_tax = to_number(data_res.get("sell_tax", ""), float)
                        is_blacklisted = to_number(data_res.get("is_blacklisted", ""), int)
                        holder_count = to_number(data_res.get("holder_count", ""), int)
                        fake_token = to_number(data_res.get("fake_token", ""), int)
                        is_airdrop_scam = to_number(data_res.get("is_airdrop_scam", ""), int)
                        trust_list = to_number(data_res.get("trust_list", ""), int)
                        
                        # CEX Info
                        is_in_cex_raw = data_res.get("is_in_cex", "")
                        is_in_cex = ""
                        if isinstance(is_in_cex_raw, dict):
                            listed = is_in_cex_raw.get("listed", "0")
                            cex_list = is_in_cex_raw.get("cex_list", [])
                            if cex_list:
                                is_in_cex = ", ".join(cex_list)
                            else:
                                is_in_cex = to_number(listed, int)
                        else:
                            is_in_cex = to_number(is_in_cex_raw, int)
                            
                        # Launchpad Info
                        launchpad_raw = data_res.get("launchpad_token", "")
                        launchpad_token = ""
                        if isinstance(launchpad_raw, dict):
                            is_launch = launchpad_raw.get("is_launchpad_token", "0")
                            l_name = launchpad_raw.get("launchpad_name", "")
                            if l_name:
                                launchpad_token = l_name
                            else:
                                launchpad_token = to_number(is_launch, int)
                        else:
                            launchpad_token = to_number(launchpad_raw, int)
                        
                        # --- เรียกใช้งาน Bot วิเคราะห์ความเสี่ยง ---
                        verdict, score = analyze_risk(
                            history_scams, is_honeypot, is_proxy, is_mintable, 
                            slippage_mod, buy_tax, sell_tax, fake_token, trust_list, is_in_cex, is_airdrop_scam, is_blacklisted
                        )
                        
                        # ยัด verdict และ score ไว้เป็นคอลัมน์แรกสุดของชุดข้อมูลใหม่ (Column E, F)
                        new_columns = [
                            verdict, score, token_name, token_sym, history_scams, creator_percent, 
                            liquidity, slippage_mod, is_mintable, cooldown, owner_address,
                            is_honeypot, is_proxy, buy_tax, sell_tax, is_blacklisted, holder_count,
                            fake_token, is_airdrop_scam, trust_list, is_in_cex, launchpad_token
                        ]
                        
                        print(f"[{get_timestamp()}] [\033[92mSUCCESS\033[0m] Node: {address[:6]}...{address[-4:]} | Status: {verdict.split()[0]:<10} | Score: {score} | {load_time:.2f}s")
                        return row_data + new_columns, "success"
                    else:
                        print(f"[{get_timestamp()}] [\033[38;5;208mNOT FOUND\033[0m] Node: {address[:6]}...{address[-4:]} | Network: {network:<4} | No data in result")
                        return row_data + ["Not Found"] * 22, "failed"
                else:
                    msg = json_data.get("message", "API Error")
                    
                    if "too many requests" in msg.lower() and attempt < max_retries - 1:
                        print(f"[{get_timestamp()}] [\033[36mRATE LIMIT\033[0m] Node: {address[:6]}...{address[-4:]} | Retrying in 10s...")
                        time.sleep(10)
                        continue
                        
                    print(f"[{get_timestamp()}] [\033[91mAPI ERROR\033[0m] Node: {address[:6]}...{address[-4:]} | Network: {network:<4} | {msg}")
                    return row_data + [f"Error: {msg}"] * 22, "failed"
            else:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                print(f"[{get_timestamp()}] [\033[91mFAILED\033[0m] Node: {address[:6]}...{address[-4:]} | HTTP {response.status_code}")
                return row_data + [f"HTTP {response.status_code}"] * 22, "failed"
                
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            err_msg = str(e).split('(')[0].strip()
            print(f"[{get_timestamp()}] [\033[91mERROR\033[0m] Node: {address[:6]}...{address[-4:]} | {err_msg}")
            return row_data + ["Error"] * 22, "failed"
            
    return row_data + ["Failed"] * 22, "failed"

def main():
    print(f"[{get_timestamp()}] [SYSTEM]  Initializing GoPlus Security Scanner...")
    print(f"[{get_timestamp()}] [SYSTEM]  Connecting to Google Sheets...")
    
    load_dotenv()
    spreadsheet_id = os.getenv('SpreadSheetID')
    
    try:
        gc = gspread.service_account(filename='credentials.json')
        sh = gc.open_by_key(spreadsheet_id)
        worksheet_in = sh.worksheet('Defi Score')
    except Exception as e:
        print(f"[{get_timestamp()}] [\033[91mERROR\033[0m]   Failed to connect to Google Sheets or find 'Defi Score' sheet: {e}")
        return

    try:
        worksheet_out = sh.worksheet('RSS')
    except gspread.WorksheetNotFound:
        print(f"[{get_timestamp()}] [SYSTEM]  Sheet 'RSS' not found. Creating a new one...")
        worksheet_out = sh.add_worksheet(title='RSS', rows="1000", cols="25")

    data = worksheet_in.get_all_values()
    if not data:
        return

    headers = data[0] if len(data) > 0 else []
    total_rows = max(0, len(data) - 1)
    print(f"[{get_timestamp()}] [SYSTEM]  Found {total_rows} rows to process.\n")
    
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36"
    })

    all_results = []
    success_count = 0
    failed_count = 0

    for index, row in enumerate(data[1:], start=2):
        # ดึงมา 4 คอลัมน์แรก (สมมติว่าเป็น A:D)
        row_data = row[:4]
        while len(row_data) < 4:
            row_data.append("")
            
        network = row[1].strip() if len(row) > 1 else ""
        address = row[2].strip() if len(row) > 2 else ""

        if not address or not network:
            all_results.append(row_data + ["N/A"] * 22)
            continue
            
        result_row, status = fetch_goplus_data(row_data, network, address, session)
        all_results.append(result_row)
        
        if status == "success":
            success_count += 1
        else:
            failed_count += 1
            
        time.sleep(3) # ดีเลย์กันโดน API แบน

    print(f"\n[{get_timestamp()}] [SYSTEM]  All queries completed. Updating Google Sheet 'RSS'...")
    
    worksheet_out.clear()
    
    out_headers = headers[:4]
    while len(out_headers) < 4:
        out_headers.append(f"Col {len(out_headers)+1}")
        
    goplus_headers = [
        "Final Verdict", "Score", "Token Name", "Symbol", 
        "History Scams", "Creator %", "Liquidity (USD)", 
        "Slippage Mod?", "Mintable?", "Cooldown?", "Owner Renounced?",
        "Honeypot?", "Proxy?", "Buy Tax", "Sell Tax", "Blacklist?", "Holders",
        "Fake Token", "Airdrop Scam", "Trust List", "In Major CEX", "Launchpad"
    ]
    out_headers.extend(goplus_headers)
    
    final_data = [out_headers] + all_results
    worksheet_out.update(values=final_data, range_name='A1')

    # แปะ Note เพื่อแจ้งเตือน (พิกัดคอลัมน์ A-Y)
    insight_notes = {
        "E1": "Bot ฟันธงให้! 🚩 SCAM = โกง 100%, ⚠️ HIGH RISK = เสี่ยงสูง, ✅ PASS = ผ่านเกณฑ์เบื้องต้น, 💎 BLUECHIP = เหรียญระดับโลก",
        "F1": "คะแนนความปลอดภัย 0-100 ยิ่งเยอะยิ่งปลอดภัย",
        "I1": "สำคัญสุด! ถ้าเลข > 0 คือไอ้นี่คือมิจฉาชีพอาชีพ เคยทำแท้งเหรียญอื่นมาแล้วกี่ครั้ง",
        "J1": "ถ้าเจ้าของถือ > 5% ก็เสียวแล้ว แต่นี่พี่แกถือ 99% คือรอเทใส่หน้าเราชัดๆ",
        "K1": "ถ้าสภาพคล่องหลักร้อย/หลักพันเหรียญ อย่าไปเข้า เสียค่าแก๊สฟรี เพราะไม่มีเงินให้เราถอน",
        "L1": "ถ้าเป็น 1 คือมันแอบแก้ 'ภาษีขาย' เป็น 99% เมื่อไหร่ก็ได้ (โดนขังลืม)",
        "M1": "ถ้าเป็น 1 คือเจ้าของเสกเหรียญเพิ่มมาทุบราคาได้เรื่อยๆ ไม่จบสิ้น",
        "N1": "ถ้าเป็น 1 มันอาจจะกักเราไม่ให้ขายทันทีตอนราคากำลังร่วง",
        "O1": "ถ้าไม่ใช่ 0x000... แปลว่าเจ้าของยังมีกุญแจไขบ้านมาขโมยของได้ตลอดเวลา",
        "P1": "ขายได้ไหม ถ้าเป็น 1 คือมิจฉาชีพ 100%",
        "Q1": "แก้สัญญาได้ไหม ถ้าเป็น 1 (และไม่ใช่เหรียญ Bluechip) ระวังโดนสับขาหลอก",
        "R1": "ภาษีขาซื้อ ถ้าเกิน 10-15% เสี่ยง",
        "S1": "ภาษีขาขาย ถ้าเกิน 10-15% เสี่ยง",
        "T1": "แบนเราได้ไหม ถ้าเป็น 1",
        "U1": "จำนวนคนถือถ้าน้อยกว่า 100 (ยกเว้นเหรียญเพิ่งเกิด)",
        "V1": "1 = เหรียญปลอม ลอกเลียนแบบเหรียญดัง (เช็คชื่อดีๆ มันชอบปลอมเป็นเหรียญ Top)",
        "W1": "1 = เหรียญขยะที่ส่งเข้ากระเป๋าเราฟรีๆ เพื่อหลอกให้เราไปกดอนุมัติ (Approve) แล้วดูดเงิน",
        "X1": "1 = เหรียญดังที่น่าเชื่อถือ (มีประวัติดีและได้รับการตรวจสอบสูง)",
        "Y1": "ถ้ามีชื่อ Binance/OKX ฯลฯ แปลว่าเหรียญนี้ลิสต์บนกระดานเทรดใหญ่แล้ว (ปลอดภัยสูง)",
        "Z1": "1 = เหรียญที่เกิดจาก Platform ดัง (เช่น four.meme) มักจะตรวจสอบ Code มาดีระดับหนึ่ง"
    }
    
    try:
        worksheet_out.update_notes(insight_notes)
        print(f"[{get_timestamp()}] [SYSTEM]  Added insight notes to headers successfully!")
    except AttributeError:
        print(f"[{get_timestamp()}] [\033[93mWARNING\033[0m] worksheet.update_notes is not supported in this gspread version.")

    print(f"[{get_timestamp()}] [SYSTEM]  Sheet 'RSS' updated successfully!")
    print(f"[{get_timestamp()}] [SYSTEM]  Summary: Processed {success_count + failed_count} (Success: \033[92m{success_count}\033[0m, Failed: \033[91m{failed_count}\033[0m)")

if __name__ == "__main__":
    main()