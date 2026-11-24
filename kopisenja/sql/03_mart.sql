-- 04 MARTS: the answers the owner actually asks for.

-- Profit per channel per month (after commission and cost of goods)
CREATE OR REPLACE TABLE mart_channel_bulanan AS
SELECT strftime(tgl, '%Y-%m') AS bulan, channel,
       sum(omzet) AS omzet, sum(komisi_rp) AS komisi_rp, sum(laba) AS laba,
       round(sum(laba) * 100.0 / nullif(sum(omzet), 0), 1) AS margin_persen
FROM fact_penjualan GROUP BY ALL ORDER BY bulan, omzet DESC;

-- Products: best sellers and slow movers
CREATE OR REPLACE TABLE mart_produk AS
WITH p AS (
  SELECT produk, sum(qty) AS terjual, sum(omzet) AS omzet, sum(laba) AS laba,
         round(sum(laba) * 100.0 / nullif(sum(omzet), 0), 1) AS margin_persen
  FROM fact_penjualan GROUP BY produk
)
SELECT *, rank() OVER (ORDER BY omzet DESC) AS peringkat,
       CASE WHEN terjual < 0.05 * max(terjual) OVER () THEN 'kurang laku' ELSE '' END AS catatan
FROM p ORDER BY omzet DESC;

-- Busy hours (in-store + delivery apps), transactions per day-of-week x hour
CREATE OR REPLACE TABLE mart_jam AS
SELECT hari, jam, count(DISTINCT sumber || id_transaksi) AS transaksi
FROM fact_penjualan WHERE channel <> 'Shopee'
GROUP BY ALL ORDER BY hari, jam;

-- Daily revenue per channel (for trend charts)
CREATE OR REPLACE TABLE mart_harian AS
SELECT tgl, channel, sum(omzet) AS omzet, sum(laba) AS laba
FROM fact_penjualan GROUP BY ALL ORDER BY tgl, channel;
