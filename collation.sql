ALTER DATABASE hastane
  CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_turkish_ci;

ALTER TABLE doktor
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE hasta
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_olcum
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_semptom
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_egzersiz_oneri
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_diyet_plani
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_egzersiz_takip
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_diyet_takip
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;
ALTER TABLE tbl_insulin
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_turkish_ci;