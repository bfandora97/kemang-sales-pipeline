-- 03 FACT TABLE: one clean row per sale line, with ONE product name, channel, commission and real profit.
-- Product names are matched case-insensitively through the alias table (config/alias.csv).
CREATE OR REPLACE TABLE fact_penjualan AS
SELECT
  s.sumber,
  s.id_transaksi,
  CAST(s.waktu AS DATE)                      AS tgl,
  hour(s.waktu)                              AS jam,
  dayofweek(s.waktu)                         AS hari,        -- 0 = Sunday
  c.channel,
  p.produk,
  s.qty,
  s.omzet,
  CAST(round(s.omzet * c.komisi) AS BIGINT)  AS komisi_rp,
  s.qty * p.hpp                              AS hpp_rp,
  s.omzet - CAST(round(s.omzet * c.komisi) AS BIGINT) - s.qty * p.hpp AS laba
FROM stg_unik s
JOIN ref_alias   a ON a.sumber = s.sumber AND lower(a.nama_asli) = lower(s.nama_asli)
JOIN ref_produk  p ON p.produk = a.produk
JOIN ref_channel c ON c.sumber = s.sumber;
