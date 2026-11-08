/**
 * Bahasa Indonesia for every string the interface wraps in `t("…")` or `msg("…")`.
 * ===============================================================================
 *
 * THE KEY IS THE ENGLISH, EXACTLY as the component writes it, placeholders and
 * all. `scripts/check_frontend.mjs` fails the build when a wrapped string has no
 * entry here, when an entry's `{placeholders}` differ from its key's, and when an
 * entry is no longer used by any component. Keep this file plain JSON inside the
 * braces — double-quoted strings, one entry per line, comments only on lines of
 * their own — because that check reads it as JSON.
 *
 * THE WORDS, chosen once and used everywhere (the server's prose uses the same):
 *   lens → lensa · Flow → Arus · Trend → Tren · Value → Nilai · Quality → Kualitas
 *   Guided / Full → Terpandu / Lengkap · reading mode → mode baca
 *   holding horizon → jangka waktu kepemilikan · base rate → tingkat dasar
 *   fair value → nilai wajar · intrinsic value → nilai intrinsik
 *   free cash flow → arus kas bebas · discount rate → tingkat diskonto
 *   terminal value → nilai terminal · drawdown → penurunan dari puncak
 *   overbought / oversold → jenuh beli / jenuh jual · moving average → rata-rata bergerak
 *   support / resistance → support / resistance (as IDX traders write them)
 *   yield → imbal hasil · balance sheet → neraca · net income → laba bersih
 *   revenue → pendapatan · watchlist → daftar pantau · thesis → tesis
 *   not investment advice → bukan saran investasi · IDX → BEI in prose
 *
 * The reader is addressed as "Anda". Tickers, numbers, units and every
 * identifier stay as they are; so do the names of published models and screens
 * (Piotroski F-Score, Altman Z, Beneish M, CAPM, DCF), which an Indonesian
 * reader searches for under those names.
 */
export const ID: Record<string, string> = {
  // ---- Shell: top bar, menu, preferences --------------------------------------
  "Markets": "Pasar",
  "Compare": "Bandingkan",
  "Journal": "Jurnal",
  "Field manual": "Panduan",
  "Search or jump to…": "Cari atau lompat ke…",
  "Search": "Cari",
  "QuantDesk home": "Beranda QuantDesk",
  "Open menu": "Buka menu",
  "Close menu": "Tutup menu",
  "Menu": "Menu",
  "Main": "Utama",
  "Reading mode": "Mode baca",
  "Language": "Bahasa",
  "Guided": "Terpandu",
  "Full": "Lengkap",

  // ---- Command palette --------------------------------------------------------
  "Open": "Buka",
  "Recent": "Terakhir dibuka",
  "Watchlist": "Daftar pantau",
  "Go to": "Ke halaman",
  "Actions": "Tindakan",
  "Settings": "Pengaturan",
  "Open {symbol}": "Buka {symbol}",
  "as typed": "sesuai ketikan",
  "Indonesia (IDX)": "Indonesia (BEI)",
  "Home": "Beranda",
  "Markets: what moved today": "Pasar: apa yang bergerak hari ini",
  "Markets: rank a universe": "Pasar: urutkan sekumpulan saham",
  "Markets: anomaly screener": "Pasar: penyaring anomali",
  "Markets: what a universe moves with": "Pasar: apa yang menggerakkan sekumpulan saham",
  "Compare companies": "Bandingkan perusahaan",
  "Thesis journal": "Jurnal tesis",
  "Switch to Full mode": "Beralih ke mode Lengkap",
  "Switch to Guided mode": "Beralih ke mode Terpandu",
  "Switch to Bahasa Indonesia": "Beralih ke Bahasa Indonesia",
  "Switch to English": "Beralih ke bahasa Inggris",
  "Holding horizon: {n} year": "Jangka waktu kepemilikan: {n} tahun",
  "Holding horizon: {n} years": "Jangka waktu kepemilikan: {n} tahun",
  "current": "saat ini",
  "Search and commands": "Pencarian dan perintah",
  "Company name, ticker, or a page to go to": "Nama perusahaan, ticker, atau halaman yang dituju",
  "Company name or ticker, or a page to go to": "Nama perusahaan atau ticker, atau halaman yang dituju",
  "searching…": "mencari…",
  "Results": "Hasil",
  "No listing or page matches. Type a full symbol — BTC-USD, ^GSPC — to open it as typed.": "Tidak ada emiten atau halaman yang cocok. Ketik simbol lengkap — BTC-USD, ^GSPC — untuk membukanya apa adanya.",
  "move": "pindah",
  "open": "buka",
  "Listings as of {us} (US) · {id} (IDX)": "Daftar emiten per {us} (AS) · {id} (BEI)"
};
