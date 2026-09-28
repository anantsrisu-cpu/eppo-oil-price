# ความปลอดภัยของระบบ

## หลักการออกแบบ: ไม่มีอะไรให้แฮก

| ความเสี่ยง | การป้องกันในระบบนี้ |
|---|---|
| เซิร์ฟเวอร์/ฐานข้อมูลถูกเจาะ | **ไม่มีเซิร์ฟเวอร์และฐานข้อมูลออนไลน์** — Dashboard เป็นไฟล์ static บน GitHub Pages (HTTPS) ผู้ใช้ดาวน์โหลดได้อย่างเดียว |
| รหัสผ่าน/Token รั่ว | **ไม่มี secret ใด ๆ** — ข้อมูล สนพ. เป็นสาธารณะ ไม่ต้อง login. การ commit ใช้ `GITHUB_TOKEN` ชั่วคราวที่ GitHub ออกให้ต่อรัน (หมดอายุเมื่อรันจบ), deploy ใช้ OIDC |
| เครือข่ายองค์กรถูกโจมตีผ่านระบบนี้ | GitHub เป็นตัวกลาง: runner ของ GitHub เป็นฝ่ายเชื่อมต่อ สนพ. — เครือข่ายองค์กรไม่ต้องเปิดพอร์ต ไม่ต้องเชื่อมเว็บภายนอก ผู้ใช้เพียงเปิดดูหน้า github.io |
| สคริปต์ถูกหลอกให้ต่อเว็บอันตราย / ส่งข้อมูลออก | 2 ชั้น: (1) **harden-runner block mode** บล็อกทุกการเชื่อมต่อขาออกที่ไม่อยู่ใน allow-list (eppo.go.th, github, pypi) (2) โค้ด `http.py` มี allow-list โฮสต์, บังคับ HTTPS + ตรวจใบรับรอง, ตรวจ redirect, จำกัดขนาด 5 MB, timeout |
| ข้อมูลต้นทางถูกปลอม/ผิดพลาด | ตรวจช่วงราคา 10–100 บาท, จำนวนแบรนด์/ราคาขั้นต่ำ, ห้ามซ้ำ, แจ้งเตือนราคากระโดด >15%, ตรวจยอดโครงสร้างราคารวมเท่าราคาขายปลีก — ถ้าไม่ผ่าน **ไม่ commit** |
| XSS / โค้ดแปลกปลอมใน Dashboard | CSP เข้มงวด (`script-src 'self'`, ห้าม inline script, ห้ามโหลดจากโดเมนอื่น), **ไม่มี JavaScript ภายนอก/CDN**, ข้อความจากข้อมูลใส่ด้วย `textContent` เท่านั้น |
| CSV/Excel formula injection | ข้อความที่ขึ้นต้นด้วย `= + - @` ถูกใส่ `'` นำหน้าในไฟล์ Excel/CSV ที่ export |
| Supply-chain (แพ็กเกจ/Action ถูกแทรกโค้ด) | Python ใช้แพ็กเกจภายนอก **ตัวเดียว** (openpyxl) ล็อกเวอร์ชัน + **SHA-256 hash**; GitHub Actions **ล็อกด้วย commit SHA**; Dependabot แจ้งอัปเดตทุกสัปดาห์; จำกัด Action ที่อนุญาตในการตั้งค่า repo |
| สิทธิ์ workflow มากเกินจำเป็น | `permissions: {}` เป็นค่าเริ่มต้น; job update ได้แค่ `contents: write`; job deploy ได้แค่ `pages: write` + `id-token: write`; CI ได้แค่ `contents: read` |
| Script injection ใน workflow | input จากผู้ใช้ส่งผ่าน environment variable และตรวจรูปแบบวันที่ด้วย regex ก่อนใช้ |
| ประวัติข้อมูลถูกแก้ย้อนหลัง | ทุกการเปลี่ยนแปลงอยู่ใน git history + JSON ดิบรายวันใน `data/raw/` + ruleset ห้าม force-push/ลบ branch |

## สิ่งที่ผู้ดูแลควรทำ (checklist)

- [ ] เปิด **2FA** บัญชี GitHub ทุกคนที่มีสิทธิ์เขียน repo
- [ ] Settings → Actions → General: อนุญาต Action ของ GitHub + `step-security/harden-runner@*`, บังคับ pin SHA · Workflow permissions = Read
- [ ] Ruleset `protect-main`: Restrict deletions + Block force pushes
- [ ] เปิด Secret scanning + Push protection
- [ ] **ห้าม** ใส่รหัสผ่าน/Token/ข้อมูลภายในองค์กรลงใน repo นี้ (repo เป็น Public)
- [ ] รีวิว PR ของ Dependabot ก่อน merge (ดูว่ามาจาก dependabot จริง, CI ผ่าน)
- [ ] ถ้าใช้ self-hosted runner: ติดตั้งด้วยบัญชีสิทธิ์ต่ำ, ใช้กับ repo นี้เท่านั้น, อัปเดต Windows/Python สม่ำเสมอ

## ขอบเขตข้อมูล

ข้อมูลทั้งหมดเป็นข้อมูลสาธารณะจาก สนพ. (www.eppo.go.th) ระบบดึงวันละ 1–2 ครั้ง (backfill 1 ไฟล์/วินาที)
เพื่อไม่เป็นภาระต่อเว็บต้นทาง และระบุตัวตนใน User-Agent อย่างเปิดเผย
