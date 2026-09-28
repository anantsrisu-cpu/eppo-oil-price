# แก้ปัญหา / เจอบั๊ก ต้องดูที่ไหน

> ผู้ใช้ทั่วไป: เปิด `ติดตั้งระบบ-EPPO.html` → แท็บ **แผงควบคุม** → ตาราง "การรัน 10 ครั้งล่าสุด" กด **Log** ของแถวที่ ❌
> ปัญหาที่พบบ่อยแก้ได้ด้วยปุ่มในแผงควบคุม (ดึงใหม่ / โหมดแก้ปัญหาเครือข่าย / ตั้งค่า Pages ใหม่ / อัปเดตโปรแกรม)
> ตัวติดตั้งแจ้ง "Token ขาดสิทธิ์ workflow" → สร้าง Token ใหม่ติ๊ก `repo` + `workflow` แล้วกด "ทำต่อ" (ระบบทำต่อจากที่ค้าง)
> รันใน Actions ขึ้น ❌ ที่ job **Check fetch result** แต่ Deploy ✅ = Dashboard อัปเดตแล้วด้วยข้อมูลเดิม แต่ดึงจาก สนพ. ไม่ได้ในรอบนั้น

## 1. ดูว่าเกิดอะไรขึ้น (เริ่มที่นี่เสมอ)

1. แท็บ **Actions** → คลิกรันที่ ❌ → job **Fetch EPPO data & build** → กางขั้นตอนที่แดง อ่านบรรทัด `ERROR`
2. เปิด `data/run_log.csv` — ทุกการรันมี 1 แถว: `status` = `ok` / `error` / `blocked` + ข้อความ error
3. หน้า **Summary** ของรัน และ `reports/latest.md` — มีส่วน *warnings* (คำเตือนคุณภาพข้อมูล)
4. รันบนเครื่องตัวเองแบบละเอียด: `python scripts/fetch_daily.py -v`

## 2. ตารางอาการ → สาเหตุ → วิธีแก้

| อาการ / ข้อความ | สาเหตุ | วิธีแก้ |
|---|---|---|
| `EPPO firewall (Cloudflare) blocked this request` / status `blocked` | Cloudflare ของ สนพ. บล็อก IP ของ GitHub ชั่วคราว | รอรอบ 11:35 น. / กด Re-run ภายหลัง. ถ้าเป็นหลายวันติด → ใช้ self-hosted runner ([SETUP ขั้นที่ 9](SETUP.md)) |
| `Network error … timed out` | เว็บ สนพ. ช้า/ล่ม | ระบบ retry 4 ครั้ง (5→10→20 วินาที) อยู่แล้ว รอรอบถัดไป หรือเพิ่ม `HTTP_TIMEOUT` ใน `config.py` |
| ขั้น *Harden runner* แจ้ง blocked / ขั้นอื่นต่อเน็ตไม่ได้ (เช่น pip, upload) | โดเมนนั้นไม่อยู่ใน allow-list | เปิดรัน → ลิงก์ *StepSecurity insights* ดูโดเมนที่ถูกบล็อก → เพิ่มใน `allowed-endpoints` ใน `daily-update.yml`. แก้ด่วนชั่วคราว: ตั้ง Variable `EGRESS_POLICY` = `audit` แล้วลบทิ้งเมื่อแก้เสร็จ |
| `EPPO API status is not success` / `'data' missing` | สนพ. เปลี่ยนรูปแบบ API | เปิด `https://www.eppo.go.th/wp-json/oil-api/v1/oil-prices` ในเบราว์เซอร์ เทียบกับ `data/raw/api/…` วันก่อนหน้า แล้วแก้ `scripts/eppo/api.py` |
| `only N prices returned` / `only N brands returned` | API ส่งข้อมูลมาไม่ครบ (มักชั่วคราว) | รอรอบถัดไป. ถ้าถาวร (เช่นแบรนด์เลิกกิจการ) ลด `MIN_BRANDS_EXPECTED` / `MIN_PRICES_EXPECTED` ใน `config.py` |
| `price out of range: …` | ตัวเลขผิดปกติ (<10 หรือ >100 บาท) | ตรวจไฟล์ `data/raw/api/…` ถ้าราคาจริงสูงขึ้นมาก ให้ปรับ `PRICE_MIN/PRICE_MAX` |
| warning `NEW brand code from EPPO: 'xxx'` | สนพ. เพิ่มแบรนด์ใหม่ | เพิ่ม `"xxx": {...}` ใน `BRANDS` (`config.py`) และสีใน `site/assets/style.css` (`--b-xxx`) — ระหว่างนี้ข้อมูลยังถูกเก็บไว้ครบ |
| warning `NEW product code from EPPO: 'xxx'` | ชนิดน้ำมันใหม่ | เพิ่มใน `PRODUCTS` (`config.py`) |
| warning `brand esso: effective date … days old -> marked stale` | สนพ. ยังคืนราคาเก่าของแบรนด์นั้น | ปกติ (เอสโซ่) — ไม่นำไปคำนวณ. ถ้าแบรนด์กลับมาอัปเดต ระบบปลดสถานะเองอัตโนมัติ |
| `structure file … skipped: header row with 'RETAIL' not found` | สนพ. เปลี่ยน layout Excel | ดาวน์โหลดไฟล์นั้นมาเปิดดูหัวคอลัมน์ แล้วแก้ `STRUCTURE_COLUMN_MAP` / `STRUCTURE_PRODUCT_MAP` ใน `config.py` |
| `structure file … skipped: not an .xlsx file` | ลิงก์ไฟล์ของ สนพ. เสีย (เคยพบ 17–19 เม.ย. 69 ได้ 404) | ข้ามได้ วันนั้นใช้ราคาวันก่อนหน้าต่อ |
| warning `unknown structure row 'XXX'` | ชื่อแถวสินค้าใน Excel เปลี่ยน/สะกดผิด | เพิ่มคู่ `"XXX": "code"` ใน `STRUCTURE_PRODUCT_MAP` |
| warning `big move …` | ราคาเปลี่ยน >15% ใน 1 วัน | ตรวจกับหน้าเว็บ สนพ. ว่าจริงหรือไม่ (ไม่หยุดระบบ) |
| `ERROR: THESE PACKAGES DO NOT MATCH THE HASHES` | แก้ `requirements.txt` ไม่ครบ | ใช้เวอร์ชัน + hash ตาม PR ของ Dependabot เท่านั้น |
| `git push` rejected | มีคนแก้ repo พร้อมกัน | ระบบ `pull --rebase` ให้ 3 ครั้งแล้ว — กด Re-run |
| Dashboard 404 | Pages ยังไม่ได้ตั้งเป็น GitHub Actions / ยังไม่เคย deploy สำเร็จ | [SETUP ขั้นที่ 4](SETUP.md) แล้วรัน mode `rebuild` |
| Dashboard ไม่อัปเดต | เบราว์เซอร์ cache หรือ job deploy ล้ม | กด Ctrl+F5 / ดู job **deploy** |
| ไม่มีรันตามเวลาเลย | Actions ถูกปิด หรือ GitHub ปิด schedule หลัง repo ไม่มีความเคลื่อนไหว 60 วัน | Actions → เลือก workflow → **Enable workflow** |
| `…oil_prices.sqlite not found` (บนเครื่อง) | ยังไม่ได้ build | `python scripts/build_outputs.py` |
| Dashboard ขึ้น "โหลดข้อมูลไม่สำเร็จ" เมื่อเปิดไฟล์ตรง ๆ | เปิด `index.html` แบบ file:// | เปิดผ่าน `python -m http.server 8000 --directory _site` |

## 3. แก้ข้อมูลผิดด้วยมือ

1. แก้ `data/retail_prices_brand.csv` หรือ `data/price_structure_daily.csv` (Excel/Notepad แล้ว Save เป็น CSV UTF-8)
2. `python scripts/build_outputs.py` เพื่อตรวจ → commit + push
3. หรือบน GitHub: Actions → Run workflow → mode **rebuild**

## 4. ดึงข้อมูลวันที่ขาดย้อนหลัง

- **ราคารายแบรนด์**: API ให้เฉพาะ "ราคาวันนี้" — วันที่รันพลาดดึงย้อนไม่ได้
  (ระบบเติมให้เองจาก `effective_date` ของ API ถ้าราคาไม่เปลี่ยน และใช้ราคาล่าสุดต่อสูงสุด 10 วัน)
- **ราคา ปตท./โครงสร้างราคา**: `Run workflow` → mode `backfill` + วันที่เริ่ม
  หรือ `python scripts/backfill_structure.py --start 2026-09-01 --force`

## 5. ตรวจว่าโค้ดยังถูกต้องหลังแก้

```bash
python -m unittest discover -s tests -v
```
ทุกการ push จะรัน `ci.yml` ให้อัตโนมัติ — ถ้า ❌ อย่าเพิ่ง merge
