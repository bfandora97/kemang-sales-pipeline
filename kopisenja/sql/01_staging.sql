-- 01 STAGING: every source into ONE shape. Raw tables stay untouched (all text, exactly as exported).
-- Names: trimmed + inner double spaces collapsed. Timestamps parsed per source format.
CREATE OR REPLACE TABLE stg_penjualan AS
SELECT 'kasir_kemang' AS sumber, "No Struk" AS id_transaksi,
       strptime("Tanggal" || ' ' || "Jam", '%d/%m/%Y %H:%M') AS waktu,
       regexp_replace(trim("Nama Item"), '\s+', ' ', 'g') AS nama_asli,
       CAST("Qty" AS INTEGER) AS qty, CAST("Total" AS BIGINT) AS omzet
FROM raw_kasir_kemang
UNION ALL
SELECT 'kasir_tebet', receipt_no,
       strptime("date" || ' ' || "time", '%Y-%m-%d %H:%M:%S'),
       regexp_replace(trim(item), '\s+', ' ', 'g'),
       CAST(qty AS INTEGER), CAST(amount AS BIGINT)
FROM raw_kasir_tebet
UNION ALL
SELECT 'gofood', "Order ID",
       strptime("Order Time", '%Y-%m-%d %H:%M:%S'),
       regexp_replace(trim("Item Name"), '\s+', ' ', 'g'),
       CAST("Quantity" AS INTEGER), CAST("Gross Sales" AS BIGINT)
FROM raw_gofood
UNION ALL
SELECT 'shopee', "No. Pesanan",
       strptime("Waktu Pesanan Dibuat", '%Y-%m-%d %H:%M'),
       regexp_replace(trim("Nama Produk"), '\s+', ' ', 'g'),
       CAST("Jumlah" AS INTEGER), CAST("Total Harga Produk" AS BIGINT)
FROM raw_shopee;

-- 02 DEDUPLICATE: exports sometimes repeat the same line. Same source + receipt + item + qty + amount = one sale.
CREATE OR REPLACE TABLE stg_unik AS
SELECT * EXCLUDE (rn) FROM (
  SELECT *, row_number() OVER (PARTITION BY sumber, id_transaksi, nama_asli, qty, omzet ORDER BY waktu) AS rn
  FROM stg_penjualan
) WHERE rn = 1;
