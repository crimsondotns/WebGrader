import os
import cloudscraper
from bs4 import BeautifulSoup
import time
from datetime import datetime
from urllib.parse import urlparse
import gspread
from dotenv import load_dotenv

# บังคับเปิดใช้งาน ANSI Colors สำหรับ Windows Terminal
os.system('') 

def get_timestamp():
    return datetime.now().strftime("%a, %d %b %y %H:%M:%S")

class WebRaterBot:
    def __init__(self, url, symbol="UNK"):
        if not url.startswith('http'):
            self.url = 'https://' + url
        else:
            self.url = url
            
        self.symbol = symbol 
        self.domain = urlparse(self.url).netloc
        self.score = 0
        self.results = {}
        self.is_success = False
        self.error_msg = ""
        self.scraper = cloudscraper.create_scraper() # สร้าง scraper ครั้งเดียว

    def analyze(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36'
        }
        
        try:
            start_time = time.time()
            # ใช้ scraper แทน requests เพื่อกัน 403
            response = self.scraper.get(self.url, headers=headers, timeout=15)
            load_time = time.time() - start_time
            
            # 1. เช็ค Status Code พื้นฐานก่อน (ถ้าเป็น 4xx หรือ 5xx ถือว่าพังทันที)
            if response.status_code >= 400:
                self.is_success = False
                self.error_msg = f"HTTP Error {response.status_code}"
            else:
                soup = BeautifulSoup(response.text, 'html.parser')
                html_content = response.text.lower()
                
                # 2. 🛠️ เช็ค Blacklist หน้า Error Page ของ Framer, Cloudflare ฯลฯ
                is_broken, broken_reason = self.check_if_broken(soup, html_content)
                
                if is_broken:
                    self.is_success = False
                    self.error_msg = broken_reason
                else:
                    # 3. ถ้าผ่านทุกด่าน ถึงจะเริ่มให้คะแนน
                    self.check_speed(load_time)
                    self.check_security()
                    self.check_seo(soup)
                    self.check_ux_ui(soup, html_content)
                    self.check_social_sharing(soup)
                    self.is_success = True
            
        except Exception as e:
            self.is_success = False
            self.error_msg = str(e)

        self.print_log()

    def check_if_broken(self, soup, html_content):
        blacklist_phrases = [
            "there is no site configured at this address", # Framer
            "site not found", # Framer
            "origin dns error", # Cloudflare
            "error 1016", # Cloudflare
            "domain has expired", # เว็บหมดอายุ
            "domain is parked", # โดเมนว่าง
            "404 not found" # Error ทั่วไป
        ]
        
        # กวาดหาคำต้องห้ามใน HTML
        for phrase in blacklist_phrases:
            if phrase in html_content:
                return True, f"Detected Error Page: '{phrase.title()}'"
                
        # เช็คจาก Title เผื่อไว้
        title = soup.title.string.lower() if soup.title and soup.title.string else ""
        if "error" in title or "not found" in title:
             return True, "Detected Error Page from Title Tag"

        return False, "" 

    def check_speed(self, load_time):
        if load_time < 2:
            score, log_msg, sheet_msg = 20, f"Fast load time ({load_time:.2f}s)", f"✅ โหลดเร็วมาก ({load_time:.2f}s)"
        elif load_time < 5:
            score, log_msg, sheet_msg = 10, f"Medium load time ({load_time:.2f}s)", f"⚠️ โหลดปานกลาง ({load_time:.2f}s)"
        else:
            score, log_msg, sheet_msg = 0, f"Slow load time ({load_time:.2f}s)", f"❌ โหลดช้ามาก ({load_time:.2f}s)"
        self.score += score
        self.results['Speed'] = {'score': score, 'log_reason': log_msg, 'sheet_text': sheet_msg}

    def check_security(self):
        if self.url.startswith('https'):
            score, log_msg, sheet_msg = 20, "Valid HTTPS connection", "✅ มี HTTPS ปลอดภัย"
        else:
            score, log_msg, sheet_msg = 0, "Missing HTTPS secured connection", "❌ ไม่มี HTTPS"
        self.score += score
        self.results['Security'] = {'score': score, 'log_reason': log_msg, 'sheet_text': sheet_msg}

    def check_seo(self, soup):
        score, details = 0, []
        if soup.title and soup.title.string:
            score += 10
            details.append("Title")
        if soup.find('meta', attrs={'name': 'description'}):
            score += 10
            details.append("Description")
            
        if score == 20:
            log_msg, sheet_msg = "Title and Description present", "✅ โครงสร้างครบ"
        elif score == 10:
            log_msg, sheet_msg = f"Partial tags (Found {details[0]}, missing other)", "⚠️ ขาดหายบางส่วน"
        else:
            log_msg, sheet_msg = "No SEO tags found", "❌ ไม่มีโครงสร้างพื้นฐาน"
        self.score += score
        self.results['SEO'] = {'score': score, 'log_reason': log_msg, 'sheet_text': sheet_msg}

    def check_ux_ui(self, soup, html_content):
        score, details = 0, []
        if soup.find('meta', attrs={'name': 'viewport'}):
            score += 10
            details.append("Viewport configured")

        modern_tech = ['<canvas', 'webgl', 'gsap', 'three.js', 'react', 'vue']
        found = [tech for tech in modern_tech if tech in html_content]
        if found:
            score += 10
            details.append(f"advanced UI ({found[0]})")

        if score == 20:
            log_msg, sheet_msg = f"{', '.join(details)}", "✅ ยอดเยี่ยม"
        elif score == 10:
            log_msg, sheet_msg = f"Partial UI support ({details[0]} only)", "⚠️ ปานกลาง"
        else:
            log_msg, sheet_msg = "Not responsive, no advanced UI", "❌ ไม่รองรับ"
        self.score += score
        self.results['UX/UI'] = {'score': score, 'log_reason': log_msg, 'sheet_text': sheet_msg}

    def check_social_sharing(self, soup):
        score = 0
        has_og = soup.find('meta', attrs={'property': 'og:image'}) or soup.find('meta', attrs={'property': 'og:title'})
        has_tw = soup.find('meta', attrs={'name': 'twitter:card'}) or soup.find('meta', attrs={'name': 'twitter:image'})
        
        if has_og: score += 10
        if has_tw: score += 10

        if score == 20:
            log_msg, sheet_msg = "Valid Open Graph and Twitter metadata", "✅ รองรับครบถ้วน"
        elif score > 0:
            log_msg, sheet_msg = "Partial social metadata (Missing OG or Twitter)", "⚠️ รองรับบางส่วน"
        else:
            log_msg, sheet_msg = "No Open Graph or Twitter metadata", "❌ ไม่รองรับ"
        self.score += score
        self.results['Social'] = {'score': score, 'log_reason': log_msg, 'sheet_text': sheet_msg}

    def get_grade(self):
        if not self.is_success: return "N/A"
        if self.score >= 90: return "A"
        elif self.score >= 75: return "B"
        else: return "C"

    def get_color(self):
        if not self.is_success: return "\033[91m"       # แดง (Error)
        if self.score >= 90: return "\033[92m"          # เขียว (90-100)
        elif self.score >= 75: return "\033[93m"        # เหลือง (75-89)
        else: return "\033[38;5;208m"                   # ส้ม (Grade C / 0-74)

    def print_log(self):
        t = get_timestamp()
        c = self.get_color()
        r = "\033[0m"
        
        if self.is_success:
            print(f"[{t}] [SUCCESS] Target: {self.symbol:<5} | Grade: {c}{self.get_grade():<3}{r} | Score: {c}{self.score:>2}/100{r} | {self.url}")
            
            def print_row(prefix, name, data):
                reason_padded = f"{data['log_reason']} ".ljust(55, '.')
                print(f"                     {prefix} {name:<8} : {reason_padded} [{data['score']:>2}/20]")

            print_row("├─", "Speed", self.results['Speed'])
            print_row("├─", "Security", self.results['Security'])
            print_row("├─", "SEO", self.results['SEO'])
            print_row("├─", "UX/UI", self.results['UX/UI'])
            print_row("└─", "Social", self.results['Social'])
        else:
            print(f"[{t}] [{c}FAILED{r}]  Target: {self.symbol:<5} | Grade: {c}N/A{r} | Score: {c}  0/100{r} | {self.url}")
            print(f"                     └─ {c}Error    : {self.error_msg}{r}")

def main():
    print(f"[{get_timestamp()}] [SYSTEM]  Initializing Web Rater Bot (Cloudscraper + Batch Mode)")
    print(f"[{get_timestamp()}] [SYSTEM]  Connecting to Google Sheets...")
    
    load_dotenv()
    spreadsheet_id = os.getenv('SpreadSheetID')
    sheet_name = os.getenv('SheetName')
    
    try:
        gc = gspread.service_account(filename='credentials.json')
        sh = gc.open_by_key(spreadsheet_id)
        worksheet_in = sh.worksheet(sheet_name)
    except Exception as e:
        print(f"[{get_timestamp()}] [\033[91mERROR\033[0m]   Failed to connect to Google Sheets: {e}")
        return

    try:
        worksheet_out = sh.worksheet('Graded')
    except gspread.WorksheetNotFound:
        print(f"[{get_timestamp()}] [SYSTEM]  Sheet 'Graded' not found. Creating a new one...")
        worksheet_out = sh.add_worksheet(title='Graded', rows="1000", cols="20")

    data = worksheet_in.get_all_values()
    total_rows = len(data) - 1
    print(f"[{get_timestamp()}] [SYSTEM]  Found {total_rows} rows to process.\n")

    all_results = []
    success_count = 0
    failed_count = 0

    for index, row in enumerate(data[1:], start=2): 
        if len(row) < 4: continue
            
        symbol = row[0].strip()   
        chain = row[1].strip()    
        contract = row[2].strip() 
        website = row[3].strip()  

        if not website: continue

        bot = WebRaterBot(website, symbol=symbol)
        bot.analyze()

        if bot.is_success:
            result_row = [
                symbol, chain, contract, bot.url, bot.score, bot.get_grade(),
                bot.results['Security']['sheet_text'],
                bot.results['Speed']['sheet_text'],
                bot.results['SEO']['sheet_text'],
                bot.results['UX/UI']['sheet_text'],
                bot.results['Social']['sheet_text']
            ]
            success_count += 1
        else:
            error_sheet_msg = f"❌ {bot.error_msg}"
            result_row = [symbol, chain, contract, website, 0, "N/A", error_sheet_msg, "-", "-", "-", "-"]
            failed_count += 1

        all_results.append(result_row)
        time.sleep(2) 

    # --- BATCH WRITE TO SHEET ---
    print(f"\n[{get_timestamp()}] [SYSTEM]  All scans completed. Updating Google Sheet...")
    
    # 1. ล้างข้อมูลเก่า
    worksheet_out.clear()
    
    # 2. เตรียม Header
    headers = ["Symbol", "Chain", "Contract", "Website", "Score", "Grade", "Security", "Speed", "SEO", "UX/UI", "Social"]
    
    # 3. เขียนข้อมูลใหม่แบบ Batch
    final_data = [headers] + all_results
    worksheet_out.update('A1', final_data)

    # 4. เขียน Notes ใหม่
    notes = {
        "E1": "คะแนนรวมเต็ม 100 คะแนน",
        "F1": "เกณฑ์การตัดสิน:\n- A: 90 คะแนนขึ้นไป\n- B: 75-89 คะแนน\n- C: 0-74 คะแนน\n- N/A: เว็บเข้าไม่ได้หรือโดเมนหมดอายุ",
        "G1": "Security: วัดจากใบรับรอง HTTPS (SSL Certificate)",
        "H1": "Speed: วัดจากความเร็วในการโหลด (Response Time)\n- เร็ว: < 2s\n- ปานกลาง: 2-5s\n- ช้า: > 5s",
        "I1": "SEO: วัดจากการมี Title และ Description สำหรับ Search Engine",
        "J1": "UX/UI: วัดจาก 2 ปัจจัยหลัก:\n1. Mobile Responsive: มี Viewport\n2. Modern Tech Stack: การใช้ React, Vue, GSAP, etc.",
        "K1": "Social: วัดจาก Meta Tags (Open Graph / Twitter Card)"
    }
    worksheet_out.update_notes(notes)

    print(f"[{get_timestamp()}] [SYSTEM]  Sheet updated successfully!")
    print(f"[{get_timestamp()}] [SYSTEM]  Summary: Processed {success_count + failed_count} (Success: \033[92m{success_count}\033[0m, Failed: \033[91m{failed_count}\033[0m)")

if __name__ == "__main__":
    main()