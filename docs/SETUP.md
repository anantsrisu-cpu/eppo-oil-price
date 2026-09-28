# วิธีติดตั้งระบบ

> 📕 ฉบับเต็มพร้อมภาพประกอบ: [docs/คู่มือติดตั้งและใช้งาน.pdf](คู่มือติดตั้งและใช้งาน.pdf)

มี 2 วิธี — **ผู้ใช้ทั่วไปใช้วิธีที่ 1** (ไม่ต้องเขียนโค้ด ไม่ต้องเข้าเมนู Settings ของ GitHub เอง)

---

## วิธีที่ 1 (แนะนำ) — ตัวติดตั้งอัตโนมัติ `ติดตั้งระบบ-EPPO.html`

ไฟล์นี้เป็นหน้าเว็บไฟล์เดียว มีโปรแกรมทั้งระบบฝังอยู่ข้างใน เปิดด้วย Chrome/Edge แล้วทำตาม 5 ขั้น (ประมาณ 5 นาที + รอระบบดึงข้อมูล 10–15 นาที)
หน้าติดตั้งคุยกับ `api.github.com` เท่านั้น (ล็อกด้วย Content-Security-Policy) และไม่บันทึก Token ลงเครื่อง

| ขั้น | ทำอะไร |
|---|---|
| 1 เตรียมตัว | ติ๊ก 3 ข้อ: มีบัญชี GitHub และล็อกอินใน Chrome/Edge แล้ว · เปิด 2FA · ใช้ Chrome/Edge |
| 2 สร้าง Token | กดปุ่ม **เปิดหน้าสร้าง Token บน GitHub** (ติ๊ก `repo` + `workflow` ให้แล้ว) → Expiration 7 days → Generate token → คัดลอก `ghp_…` มาวาง → **ตรวจรหัส** |
| 3 ตั้งชื่อ | ใช้ชื่อ `eppo-oil-price` ตามค่าเริ่มต้น → **เริ่มติดตั้ง** |
| 4 รอ | ระบบสร้าง repo, อัปโหลดไฟล์, ตั้งค่า Actions/Pages/ความปลอดภัย, เปิดตั้งเวลา และสั่งดึงข้อมูลย้อนหลังครั้งแรก — **ห้ามปิดหน้า** |
| 5 เสร็จ | กด **เปิด Dashboard** แล้วบันทึกลิงก์ · **ลบ Token** ที่ github.com/settings/tokens |

**⚠ จุดที่ถ้าไม่ทำ ระบบจะ Bug** (รายละเอียดในคู่มือ PDF บทที่ 2)

1. ล็อกอิน GitHub ในเบราว์เซอร์เดียวกับที่เปิดหน้าติดตั้ง
2. เปิด 2FA
3. Token ต้องมีทั้ง `repo` และ `workflow` — ขาด `workflow` จะอัปโหลดไม่ผ่าน
4. คัดลอก Token ทันที (GitHub แสดงครั้งเดียว)
5. repo ต้องเป็น Public (GitHub Pages ฟรีใช้กับ Public เท่านั้น) — ไม่งั้น Dashboard ขึ้น 404
6. ห้ามปิดหน้าติดตั้งจนขึ้น 🎉 — ถ้าเผลอปิด เปิดใหม่ ใส่ Token + ชื่อเดิม ระบบทำต่อจากที่ค้าง
7. ลบ Token หลังติดตั้งเสร็จ
8. อย่าแก้/ย้าย/ลบไฟล์ใน repo เอง โดยเฉพาะ `.github/workflows/` และหัวคอลัมน์ `data/*.csv`
9. เครือข่ายต้องเข้า `api.github.com` ได้
10. เปิดอีเมลแจ้งเตือนเมื่อรันไม่สำเร็จ และเปิด Dashboard ดูอย่างน้อยเดือนละครั้ง (GitHub หยุดตั้งเวลาเมื่อ repo ไม่เคลื่อนไหว 60 วัน)

### แผงควบคุม (ใช้ภายหลัง)

เปิดไฟล์เดิม → แท็บ **แผงควบคุม (หลังติดตั้ง)** → ใส่ Token ใหม่ + ชื่อ repo → เชื่อมต่อ มีปุ่ม:
ดึงราคาวันนี้ทันที · ดึงย้อนหลังตั้งแต่ 1 ม.ค. 2568 ใหม่ · สร้างรายงาน/Dashboard ใหม่ · อัปเดตโปรแกรมเป็นเวอร์ชันนี้ ·
โหมดแก้ปัญหาเครือข่ายชั่วคราว (`EGRESS_POLICY=audit`) / กลับเป็นโหมดปลอดภัย · ตั้งค่า Pages/ความปลอดภัยใหม่ · ตาราง 10 รันล่าสุด

> สร้างไฟล์ตัวติดตั้งใหม่หลังแก้โค้ด: `python scripts/build_installer.py` → `dist/ติดตั้งระบบ-EPPO.html`

---

## วิธีที่ 2 (สำหรับ IT) — ติดตั้งเองทีละเมนู

ใช้เมื่อองค์กรไม่อนุญาตให้ใช้ Token หรือต้องการตรวจทุกขั้นเอง ผลลัพธ์เหมือนวิธีที่ 1 ทุกประการ

**สิ่งที่ต้องมี**: บัญชี GitHub (เปิด 2FA) · Git หรือ GitHub Desktop · Python 3.12 (ไม่บังคับ — เฉพาะทดลองบนเครื่อง)

> **Public หรือ Private?** GitHub Pages ฟรีเฉพาะ repo แบบ Public (Private ต้องใช้ GitHub Pro/Team)
> ข้อมูลราคาน้ำมันเป็นข้อมูลสาธารณะของรัฐอยู่แล้ว ระบบไม่มีรหัสผ่าน/Token ใด ๆ อยู่ใน repo จึงเปิด Public ได้อย่างปลอดภัย

### ขั้นที่ 1 — สร้าง repository

1. github.com → ปุ่ม **New** → Repository name เช่น `eppo-oil-price`
2. เลือก **Public** → **ไม่ต้อง** ติ๊ก Add README (เรามี README แล้ว) → **Create repository**

### ขั้นที่ 2 — อัปโหลดไฟล์

**2.0 แตกไฟล์ให้ถูกชั้น** — คลิกขวา `eppo-oil-price.zip` → Extract All → **ลบ `\eppo-oil-price` ท้ายช่องปลายทางออก** (เช่นเหลือ `C:\Users\ชื่อคุณ\Documents`) → Extract
เปิด `Documents\eppo-oil-price` ต้องเห็น `.github`, `data`, `docs`, `reports`, `scripts`, `site`, `sql`, `tests` + 4 ไฟล์ทันที
(ถ้าเห็นแค่โฟลเดอร์ `eppo-oil-price` อีกชั้น ให้เข้าไปอีกชั้นแล้วใช้ชั้นนั้น)

**วิธี ก (แนะนำ, ไม่ต้องติดตั้งโปรแกรม)** — หน้า repo เปล่า → ลิงก์ **uploading an existing file** →
ใน File Explorer กด `Ctrl+A` เลือก *ของข้างในโฟลเดอร์* (ไม่ใช่ตัวโฟลเดอร์) → ลากไปวางในกรอบ *Drag files here…* (ใช้ Chrome/Edge)
→ ตรวจว่ามี `.github/workflows/daily-update.yml` → Commit directly to the main branch → **Commit changes**

**วิธี ข GitHub Desktop** — Sign in → File → Clone repository → เลือก eppo-oil-price → คัดลอกไฟล์ทั้งหมดจากโฟลเดอร์ที่แตก zip
ไปวางในโฟลเดอร์ที่ Clone → Summary `Initial upload` → Commit to main → Publish branch / Push origin

**วิธี ค Git command line**

```bat
git config --global user.name "ชื่อของคุณ"
git config --global user.email "อีเมล GitHub"
cd /d "%USERPROFILE%\Documents\eppo-oil-price"
dir /a /b                      &:: ต้องเห็น .github
git init -b main
git add .
git commit -m "Initial upload"
git remote add origin https://github.com/<USER>/eppo-oil-price.git
git push -u origin main         &:: หน้าต่าง Connect to GitHub → Sign in with your browser
```

**ตรวจผล**: หน้าแรกของ repo ต้องเห็น `.github` อยู่บนสุด ถ้าเห็นโฟลเดอร์ `eppo-oil-price` ซ้อนอยู่ →
Settings → General → Delete this repository แล้วทำขั้นที่ 1–2 ใหม่

### ขั้นที่ 3 — ตั้งค่า Actions (ตัวรันอัตโนมัติ)

Repo → **Settings → Actions → General**

1. **Actions permissions**: เลือก *Allow \<USER\>, and select non-\<USER\>, actions and reusable workflows*
   → ติ๊ก **Allow actions created by GitHub** → ในช่อง *Allow or block specified actions* ใส่:
   ```
   step-security/harden-runner@*
   ```
   และติ๊ก **Require actions to be pinned to a full-length commit SHA** (ถ้ามีตัวเลือกนี้)
   (อนุญาตเฉพาะ Action ที่ระบบใช้ — ป้องกัน Action แปลกปลอม)
2. **Workflow permissions**: เลือก **Read repository contents and packages permissions** (ค่าปลอดภัย)
   — workflow ขอสิทธิ์เขียนเองเฉพาะงานที่ต้อง commit ข้อมูล
3. **Fork pull request workflows**: เลือก *Require approval for all external contributors*
4. กด **Save**

### ขั้นที่ 4 — เปิด GitHub Pages

Repo → **Settings → Pages** → Build and deployment → Source: **GitHub Actions**

(environment `github-pages` จะถูกสร้างอัตโนมัติ และ deploy ได้จาก branch `main` เท่านั้น)

### ขั้นที่ 5 — ป้องกัน branch main (แนะนำ)

Settings → **Rules → Rulesets → New branch ruleset**
- Name: `protect-main` · Enforcement: Active · Target: Default branch
- ติ๊ก **Restrict deletions** และ **Block force pushes**
- (ไม่ต้องติ๊ก Require pull request — เพราะบอทต้อง commit ข้อมูลรายวันเข้า main)

เปิด **Settings → Advanced Security**: *Secret scanning* และ *Push protection* = Enable

### ขั้นที่ 6 — รันครั้งแรก (ดึงย้อนหลัง 2568 → ปัจจุบัน)

1. แท็บ **Actions** → ถ้ามีปุ่ม *I understand my workflows, go ahead and enable them* ให้กด
2. เลือก **Daily oil price update** → **Run workflow**
   - mode: **backfill** · backfill_start: `2025-01-01` → **Run workflow**
3. รอ ~10–15 นาที (ดาวน์โหลดไฟล์โครงสร้างราคา ~450 ไฟล์ อย่างสุภาพ 1 ไฟล์/วินาที)
4. เมื่อขึ้น ✅ ทั้ง 2 job (update, deploy) → คลิก job **deploy** จะเห็นลิงก์ Dashboard
   `https://<USER>.github.io/eppo-oil-price/`

> ข้อมูลตั้งต้น (ราคา ปตท. 2 ม.ค. 68 – 25 ก.ย. 69 + ราคาทุกแบรนด์ 25 ก.ย. 69) แนบมาใน repo แล้ว
> ถ้า backfill ล้มเหลว Dashboard ก็ยังมีข้อมูลให้ดู (รัน mode **rebuild** เพื่อ deploy)

### ขั้นที่ 7 — ตรวจว่ารันอัตโนมัติทุกวัน

- ตารางเวลาใน `.github/workflows/daily-update.yml` (เวลา UTC):
  - `5 3 * * *` = **10:05 น.** เวลาไทย (ดึงรอบหลัก)
  - `35 4 * * *` = **11:35 น.** (รอบสำรอง เผื่อรอบแรกล้ม/สนพ. อัปโหลดช้า — รันซ้ำไม่ทำให้ข้อมูลซ้ำ)
  - เปลี่ยนเวลา: แก้ตัวเลข (ชั่วโมงไทย − 7 = ชั่วโมง UTC) เช่น 09:30 น. → `30 2 * * *`
- GitHub อาจเริ่มช้ากว่ากำหนด 5–30 นาทีในช่วงที่คนใช้เยอะ (เป็นเรื่องปกติ)
- ทุกวันจะมี commit `data: EPPO oil prices YYYY-MM-DD` และ Dashboard อัปเดตเอง
- รายงานประจำวัน: `reports/latest.md` หรือเปิดรันใน Actions → หน้า **Summary**

### ขั้นที่ 8 — รับการแจ้งเตือนเมื่อรันไม่สำเร็จ

รูปโปรไฟล์ → **Settings → Notifications → System → Actions** → ติ๊ก *Email* และ *Only notify for failed workflows*

---

### (ทางเลือก) ขั้นที่ 9 — รันบนเครื่องในองค์กร ถ้า EPPO บล็อก IP ของ GitHub

เว็บ สนพ. ใช้ Cloudflare ถ้า run log ขึ้น `blocked` ติดต่อกันหลายวัน ให้ใช้เครื่องในออฟฟิศเป็น runner แทน
(เครื่องเป็นฝ่าย "ดึงงาน" จาก GitHub เอง ไม่ต้องเปิดพอร์ตรับจากภายนอก)

1. ติดตั้ง **Python 3.12** (ติ๊ก *Add to PATH*) และ **Git for Windows** (มี bash)
2. Repo → Settings → Actions → **Runners → New self-hosted runner** → เลือก Windows → ทำตามคำสั่งบนหน้าจอ
   (แนะนำติดตั้งเป็น service ด้วยบัญชีผู้ใช้สิทธิ์ต่ำ)
3. Repo → Settings → Secrets and variables → Actions → แท็บ **Variables** → New variable:
   `RUNNER_LABEL` = `self-hosted`
4. รัน workflow ด้วยมือ 1 ครั้งเพื่อทดสอบ — ลบตัวแปรนี้เมื่อต้องการกลับไปใช้ GitHub runner

> ความปลอดภัย: workflow ที่รันบน self-hosted มีเฉพาะ `daily-update.yml` (schedule / กดรันเอง) — ไม่มีการรันโค้ดจาก Pull Request ของคนนอกบนเครื่องนี้

---

## ทดลอง / แก้บั๊กบนเครื่องตัวเอง

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
python -m pip install --require-hashes -r requirements.txt
python -m unittest discover -s tests -v        # ทดสอบ (ไม่ต่อเน็ต)
python scripts/fetch_daily.py -v               # ดึงจริง + build
python scripts/backfill_structure.py --start 2026-09-01 --no-build   # ทดสอบอ่านไฟล์ Excel ของ สนพ.
python scripts/build_outputs.py
python -m http.server 8000 --directory _site   # เปิด http://localhost:8000
```

## ใช้งาน SQL Query

```bash
python scripts/run_query.py -f sql/queries.sql --list
python scripts/run_query.py -f sql/queries.sql -n 7              # ส่วนต่างเทียบ ปตท.
python scripts/run_query.py "SELECT * FROM v_monthly WHERE product_code='ds'" --csv diesel.csv
```
หรือเปิดไฟล์ `oil_prices.sqlite` ด้วย DB Browser for SQLite / DBeaver / Power BI (ODBC SQLite)
