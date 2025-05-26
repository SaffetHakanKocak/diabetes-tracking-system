DROP SCHEMA IF EXISTS hastane;
CREATE SCHEMA hastane
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_turkish_ci;
USE hastane;

CREATE TABLE doktor (
  kullanici_adi CHAR(11) NOT NULL PRIMARY KEY
    CHECK (kullanici_adi REGEXP '^[1-9][0-9]{10}$'),
  sifre         VARCHAR(255)   NOT NULL,
  resim         VARCHAR(255)   NOT NULL,
  email         VARCHAR(100)   NOT NULL UNIQUE,
  dogum_tarihi  DATE,
  cinsiyet      ENUM('E','K','D') DEFAULT 'E',
  isim          VARCHAR(100)   NOT NULL,
  sehir         VARCHAR(50)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE hasta (
  kullanici_adi CHAR(11) NOT NULL PRIMARY KEY
    CHECK (kullanici_adi REGEXP '^[1-9][0-9]{10}$'),
  sifre         VARCHAR(255)   NOT NULL,
  resim         VARCHAR(255)   NOT NULL,
  email         VARCHAR(100)   NOT NULL UNIQUE,
  dogum_tarihi  DATE,
  cinsiyet      ENUM('E','K','D') DEFAULT 'E',
  isim          VARCHAR(100)   NOT NULL,
  sehir         VARCHAR(50),
  doktor_tc     CHAR(11)       NOT NULL,
  FOREIGN KEY (doktor_tc)
    REFERENCES doktor(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE semptom_turleri (
  id   INT AUTO_INCREMENT PRIMARY KEY,
  tur  VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_semptom (
  hasta_tc       CHAR(11)   NOT NULL,
  tarih_saat     DATETIME   NOT NULL,
  semptom_tur_id INT        NOT NULL,
  aciklama       TEXT,
  PRIMARY KEY (hasta_tc, tarih_saat, semptom_tur_id),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE,
  FOREIGN KEY (semptom_tur_id)
    REFERENCES semptom_turleri(id)
      ON UPDATE CASCADE
      ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE diyet_turleri (
  id   INT AUTO_INCREMENT PRIMARY KEY,
  tur  VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_diyet_plani (
  hasta_tc      CHAR(11) NOT NULL,
  tarih_saat    DATETIME NOT NULL,
  diyet_tur_id  INT      NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat, diyet_tur_id),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE,
  FOREIGN KEY (diyet_tur_id)
    REFERENCES diyet_turleri(id)
      ON UPDATE CASCADE
      ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE egzersiz_turleri (
  id   INT AUTO_INCREMENT PRIMARY KEY,
  tur  VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_egzersiz_oneri (
  hasta_tc        CHAR(11) NOT NULL,
  tarih_saat      DATETIME NOT NULL,
  egzersiz_tur_id INT      NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat, egzersiz_tur_id),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE,
  FOREIGN KEY (egzersiz_tur_id)
    REFERENCES egzersiz_turleri(id)
      ON UPDATE CASCADE
      ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_olcum (
  hasta_tc    CHAR(11) NOT NULL,
  tarih_saat  DATETIME NOT NULL,
  seviye_mgdl SMALLINT NOT NULL,
  tur         ENUM('Sabah','Öğle','İkindi','Akşam','Gece') NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_insulin (
  hasta_tc   CHAR(11) NOT NULL,
  tarih_saat DATETIME NOT NULL,
  birim_u    SMALLINT NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_egzersiz_takip (
  hasta_tc           CHAR(11)      NOT NULL,
  tarih_saat         DATETIME      NOT NULL,
  yapilan_egzersiz   VARCHAR(255)  NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE tbl_diyet_takip (
  hasta_tc           CHAR(11)      NOT NULL,
  tarih_saat         DATETIME      NOT NULL,
  uygulanan_diyet    VARCHAR(255)  NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

CREATE TABLE uyarilar (
  hasta_tc   CHAR(11) NOT NULL,
  tarih_saat DATETIME NOT NULL,
  mesaj      TEXT     NOT NULL,
  okundu     BOOLEAN  NOT NULL DEFAULT FALSE,
  PRIMARY KEY (hasta_tc, tarih_saat, mesaj(100)),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;
  
ALTER TABLE uyarilar
  DROP PRIMARY KEY,
  DROP COLUMN okundu,
  ADD COLUMN durum VARCHAR(50) NOT NULL DEFAULT '' AFTER mesaj,
  ADD COLUMN `uyarı_tipi` VARCHAR(50) NOT NULL DEFAULT '' AFTER durum,
  ADD PRIMARY KEY (hasta_tc, tarih_saat, uyarı_tipi);

CREATE TABLE doktor_kan_olcum (
  hasta_tc    CHAR(11) NOT NULL,
  tarih_saat  DATETIME NOT NULL,
  seviye_mgdl SMALLINT NOT NULL,
  PRIMARY KEY (hasta_tc, tarih_saat),
  FOREIGN KEY (hasta_tc)
    REFERENCES hasta(kullanici_adi)
      ON UPDATE CASCADE
      ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_turkish_ci;

  
  
 INSERT INTO doktor (
  kullanici_adi,
  sifre,
  resim,
  email,
  dogum_tarihi,
  cinsiyet,
  isim,
  sehir
) VALUES
  ('12345678901', 'Sifre123!', 'C:\\Users\\yusuf\\OneDrive\\Masaüstü\\230202050_230202058\\Profil_fotolari\\doktor_1.jpg',   'eray.yilmaz@ornek.com',  '1980-05-10', 'E', 'Eray Yılmaz',  'Ankara'),
  ('23456789012', 'Gizli!456', 'C:\\Users\\yusuf\\OneDrive\\Masaüstü\\230202050_230202058\\Profil_fotolari\\doktor_2.jpg',   'eray.sa@ornek.com','1975-11-22', 'K', 'Ayla Demir',   'İstanbul'),
  ('34567890123', 'P4ssw0rd$', 'C:\\Users\\yusuf\\OneDrive\\Masaüstü\\230202050_230202058\\Profil_fotolari\\doktor_3.jpg', 	'eray.fd@ornek.com','1988-03-15', 'K', 'Meltem Kaya',  'İzmir');
 INSERT INTO semptom_turleri (tur) VALUES
  ('Poliüri'),('Polifaji'),('Polidipsi'),
  ('Nöropati'),('Kilo Kaybı'),('Yorgunluk'),
  ('Bulanık Görme'),('Yaraların Yavaş İyileşmesi');

INSERT INTO diyet_turleri (tur) VALUES
  ('Az Şekerli Diyet'),('Şekersiz Diyet'),('Dengeli Beslenme');

INSERT INTO egzersiz_turleri (tur) VALUES
  ('Yürüyüş'),('Bisiklet'),('Klinik Egzersiz');