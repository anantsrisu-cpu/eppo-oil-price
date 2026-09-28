-- ============================================================================
--  Example queries for _site/downloads/oil_prices.sqlite
--  Run one:   python scripts/run_query.py -f sql/queries.sql -n 1
--  List all:  python scripts/run_query.py -f sql/queries.sql --list
--
--  Tables : dim_brand, dim_product, fact_retail_daily (1 row = date x brand x product),
--           fact_api_snapshot (raw daily API rows), fact_price_structure (PTT structure)
--  Views  : v_latest, v_monthly, v_yearly, v_changes, v_vs_ptt
--  Unit   : Baht / litre
-- ============================================================================

-- [1] ราคาล่าสุดทุกแบรนด์ (แนวตั้ง)
SELECT b.name_th AS brand, p.name_th AS product, l.price, l.date, l.source
FROM v_latest l JOIN dim_brand b USING (brand_code) JOIN dim_product p USING (product_code)
ORDER BY b.sort_order, p.sort_order;

-- [2] Pivot ราคาล่าสุด: แถว = ชนิดน้ำมัน, คอลัมน์ = แบรนด์
SELECT p.name_th AS product,
  MAX(CASE WHEN brand_code='ptt'    THEN price END) AS ptt,
  MAX(CASE WHEN brand_code='bcp'    THEN price END) AS bangchak,
  MAX(CASE WHEN brand_code='shell'  THEN price END) AS shell,
  MAX(CASE WHEN brand_code='esso'   THEN price END) AS esso,
  MAX(CASE WHEN brand_code='caltex' THEN price END) AS chevron,
  MAX(CASE WHEN brand_code='irpc'   THEN price END) AS irpc,
  MAX(CASE WHEN brand_code='pt'     THEN price END) AS pt,
  MAX(CASE WHEN brand_code='susco1' THEN price END) AS susco,
  MAX(CASE WHEN brand_code='pure'   THEN price END) AS pure,
  MAX(CASE WHEN brand_code='susco2' THEN price END) AS susco_dealer
FROM v_latest JOIN dim_product p USING (product_code)
GROUP BY p.product_code ORDER BY p.sort_order;

-- [3] ค่าเฉลี่ยรายเดือนของแก๊สโซฮอล์ 95 แยกแบรนด์
SELECT month, brand_code, avg_price, min_price, max_price, days
FROM v_monthly WHERE product_code = 'gh95'
ORDER BY month DESC, brand_code;

-- [4] ค่าเฉลี่ยรายปี ทุกชนิดน้ำมัน ของ ปตท.
SELECT year, p.name_th AS product, avg_price, min_price, max_price, days
FROM v_yearly y JOIN dim_product p USING (product_code)
WHERE brand_code = 'ptt' ORDER BY year, p.sort_order;

-- [5] ประวัติการเปลี่ยนราคา ดีเซล B7 (ทุกแบรนด์) 30 ครั้งล่าสุด
SELECT date, brand_code, prev_price, price, change
FROM v_changes WHERE product_code = 'ds' ORDER BY date DESC LIMIT 30;

-- [6] จำนวนครั้งที่ปรับราคา / ปรับขึ้น / ปรับลง รายเดือน (ปตท., แก๊สโซฮอล์ 95)
SELECT substr(date,1,7) AS month, COUNT(*) AS changes,
       SUM(change > 0) AS up, SUM(change < 0) AS down, ROUND(SUM(change),2) AS net_change
FROM v_changes WHERE brand_code='ptt' AND product_code='gh95'
GROUP BY month ORDER BY month;

-- [7] ส่วนต่างราคาแต่ละแบรนด์เทียบ ปตท. (วันล่าสุด)
SELECT b.name_th AS brand, p.name_th AS product, v.price, v.ptt_price, v.diff_vs_ptt
FROM v_vs_ptt v JOIN dim_brand b USING (brand_code) JOIN dim_product p USING (product_code)
WHERE v.date = (SELECT MAX(date) FROM fact_retail_daily) AND v.brand_code <> 'ptt'
ORDER BY p.sort_order, v.diff_vs_ptt DESC;

-- [8] แบรนด์ที่ถูกที่สุดของแต่ละชนิดน้ำมัน (วันล่าสุด, ไม่รวมแบรนด์ข้อมูลเก่า)
SELECT p.name_th AS product, MIN(l.price) AS cheapest_price,
       GROUP_CONCAT(b.name_th, ', ') FILTER (WHERE l.price = m.min_price) AS brands
FROM v_latest l
JOIN (SELECT product_code, MIN(price) AS min_price FROM v_latest WHERE is_stale = 0 GROUP BY product_code) m
  USING (product_code)
JOIN dim_brand b USING (brand_code) JOIN dim_product p USING (product_code)
WHERE l.is_stale = 0
GROUP BY p.product_code ORDER BY p.sort_order;

-- [9] โครงสร้างราคา ปตท. ล่าสุด (ภาษี / กองทุน / ค่าการตลาด)
SELECT p.name_th AS product, s.date, s.ex_refinery, s.excise_tax + s.municipal_tax AS taxes,
       s.oil_fund, s.conservation_fund, s.marketing_margin, s.vat_wholesale + s.vat_marketing_margin AS vat,
       s.retail
FROM fact_price_structure s JOIN dim_product p USING (product_code)
WHERE s.date = (SELECT MAX(date) FROM fact_price_structure WHERE wholesale IS NOT NULL)
ORDER BY p.sort_order;

-- [10] ค่าการตลาดเฉลี่ยรายเดือน (จากโครงสร้างราคา) แก๊สโซฮอล์ 95 และ ดีเซล B7
SELECT substr(date,1,7) AS month, product_code, ROUND(AVG(marketing_margin),3) AS avg_marketing_margin,
       ROUND(AVG(oil_fund),3) AS avg_oil_fund, COUNT(*) AS business_days
FROM fact_price_structure WHERE product_code IN ('gh95','ds') AND marketing_margin IS NOT NULL
GROUP BY month, product_code ORDER BY month, product_code;

-- [11] ราคาสูงสุด/ต่ำสุดตั้งแต่ต้นปี 2568 (ปตท.)
SELECT p.name_th AS product, MIN(price) AS min_price, MAX(price) AS max_price,
       ROUND(MAX(price) - MIN(price), 2) AS range
FROM fact_retail_daily f JOIN dim_product p USING (product_code)
WHERE brand_code = 'ptt' AND date >= '2025-01-01'
GROUP BY p.product_code ORDER BY p.sort_order;

-- [12] ตรวจคุณภาพข้อมูล: จำนวนวันแยกตามแหล่งข้อมูล
SELECT brand_code, source, COUNT(*) AS rows, MIN(date) AS first, MAX(date) AS last
FROM fact_retail_daily GROUP BY brand_code, source ORDER BY brand_code, source;
