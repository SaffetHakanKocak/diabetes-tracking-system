import tkinter as tk
from tkinter import ttk,messagebox
from tkinter import filedialog,messagebox
from tkinter import simpledialog
import mysql.connector
import smtplib
from email.message import EmailMessage
from config import DB_CONFIG, EMAIL_CONFIG
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import bcrypt
from config import HASH_ROUNDS
from datetime import datetime, time, date
from zoneinfo import ZoneInfo
import random
from datetime import datetime
#denemeeeeeeeeeeeeeeee
# — EKLENECEK: Ölçüm aralıkları sabitleri
VALID_WINDOWS = {
    'Sabah':  (datetime.strptime("07:00", "%H:%M").time(),  datetime.strptime("08:00", "%H:%M").time()),
    'Öğle':   (datetime.strptime("12:00", "%H:%M").time(),  datetime.strptime("13:00", "%H:%M").time()),
    'İkindi': (datetime.strptime("15:00", "%H:%M").time(),  datetime.strptime("16:00", "%H:%M").time()),
    'Akşam':  (datetime.strptime("18:00", "%H:%M").time(),  datetime.strptime("19:00", "%H:%M").time()),
    'Gece':   (datetime.strptime("22:00", "%H:%M").time(),  datetime.strptime("23:00", "%H:%M").time()),
}

# 1) Kodunuzun en üstüne ekleyin:

# --- ÖNERİ KURALLARI ---
# Her satır: (seviye aralığı, semptom listesi, diyet, egzersiz)
RECOMMENDATION_RULES = [
    (lambda x: x < 70,   ["Nöropati","Polifaji","Yorgunluk"],            "Dengeli Beslenme", None),
    (lambda x: 70<=x<=110, ["Yorgunluk","Kilo Kaybı"],                  "Az Şekerli Diyet",  "Yürüyüş"),
    (lambda x: 70<=x<=110, ["Polifaji","Polidipsi"],                   "Dengeli Beslenme", "Yürüyüş"),
    (lambda x: 110<=x<=180,["Bulanık Görme","Nöropati"],                "Az Şekerli Diyet", "Klinik Egzersiz"),
    (lambda x: 110<=x<=180,["Poliüri","Polidipsi"],                    "Şekersiz Diyet",    "Klinik Egzersiz"),
    (lambda x: 110<=x<=180,["Yorgunluk","Nöropati","Bulanık Görme"],    "Az Şekerli Diyet", "Yürüyüş"),
    (lambda x: x >= 180,  ["Yaraların Yavaş İyileşmesi","Polifaji","Polidipsi"], "Şekersiz Diyet", "Klinik Egzersiz"),
    (lambda x: x >= 180,  ["Yaraların Yavaş İyileşmesi","Kilo Kaybı"],   "Şekersiz Diyet",   "Yürüyüş"),
]

def get_recommendation(seviye, semptoms):
    """
    seviye: int mg/dL
    semptoms: list[str]
    döndürür: (diyet_türü veya None, egzersiz_türü veya None)
    """
    s_set = set(semptoms)
    for cond, rule_syms, diet, ex in RECOMMENDATION_RULES:
        r_set = set(rule_syms)
        # Öneri yapabilmek için:
        # 1) seviye koşulu sağlanmalı
        # 2) semptoms listesiyle rule_syms kümeleri tam olarak eşleşmeli
        if cond(seviye) and s_set == r_set:
            return diet, ex
    # hiçbir kural tam eşleşme sağlamadıysa
    return None, None


# — EKLENECEK: İnsülin dozu hesaplama fonksiyonu
def get_insulin_dose_for_day(conn, hasta_tc: str, timestamp: str) -> tuple[float,int]:
    cur = conn.cursor()
    cur.execute(
        "SELECT AVG(seviye_mgdl) "
        "FROM tbl_olcum "
        "WHERE hasta_tc=%s AND DATE(tarih_saat)=DATE(%s)",
        (hasta_tc, timestamp)
    )
    avg = cur.fetchone()[0] or 0.0
    cur.close()

    if avg < 70:      dose = 0
    elif avg <= 110:  dose = 0
    elif avg <= 150:  dose = 1
    elif avg <= 200:  dose = 2
    else:             dose = 3

    return avg, dose
# -----------------------------------------------------
# Ortak: E-posta gönderimi
# -----------------------------------------------------
def send_email(to_email, tc, sifre, doktor_adi):
    try:
        msg = EmailMessage()
        msg['Subject'] = "Hasta Takip Sistemi Giriş Bilgileri"
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = to_email
        msg.set_content(f"""
Merhaba,

Dr. {doktor_adi} sizi Hasta Takip Sistemi'ne kaydetti.

Giriş Bilgileriniz:
TC: {tc}
Şifre: {sifre}

Sağlıklı günler dileriz.
""")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
            smtp.send_message(msg)
        return True
    except Exception as e:
        messagebox.showerror("Mail Hatası", f"E-posta gönderilemedi:\n{e}")
        return False

# -----------------------------------------------------
# Uygulama Ana Sınıfı
# -----------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hasta Takip Sistemi")
        self.state("zoomed")

        # ekran boyutları
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()

        # arka plan
        self.bg_image = ImageTk.PhotoImage(
            Image.open("background.png").resize((sw, sh), Image.LANCZOS)
        )
        # logo
        logo = Image.open("logo.png")
        logo_w = sw // 4
        logo_h = int(logo.height/logo.width * logo_w)
        self.logo_image = ImageTk.PhotoImage(logo.resize((logo_w, logo_h), Image.LANCZOS))

        # login bilgileri
        self.current_user_tc   = None   # TC
        self.current_user_name = None   # isim
        self.current_role      = None   # 'doctor' veya 'patient'
        self.history           = []

        # container
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # frame’leri oluştur
        self.frames = {}
        for F in (
    WelcomeFrame, LoginFrame,
    DoctorFrame, PatientFrame,
    DoctorOlcumFrame, SymptomFrame,
    EgzersizOnerFrame, DiyetPlanFrame,
    DataViewFrame, OlcumEntryFrame,
    EgzersizTakipFrame, DiyetTakipFrame,
    DoctorFilterFrame, DoctorGraphFrame,
    PatientGraphFrame, InsulinViewFrame,
    NewPatientFrame, PatientSymptomEntryFrame,
    UyariFrame,   # son eleman UyariFrame olmalı
):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("WelcomeFrame")

    def show_frame(self, page_name):
        # navigation history için
        if hasattr(self, 'current_frame'):
            self.history.append(self.current_frame)
        self.current_frame = page_name
        frame = self.frames[page_name]
        frame.tkraise()

    def go_back(self):
        if self.history:
            prev = self.history.pop()
            self.current_frame = prev
            self.frames[prev].tkraise()

    def get_my_patients(self):
        """Doktorun hastalarını döner [(tc,isim),...]"""
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT kullanici_adi, isim FROM hasta WHERE doktor_tc=%s",
            (self.current_user_tc,)
        )
        lst = cur.fetchall()
        cur.close(); conn.close()
        return lst

# -----------------------------------------------------
# Karşılama Ekranı
# -----------------------------------------------------
class WelcomeFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        canvas = tk.Canvas(self, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        # Arka plan
        canvas.create_image(0, 0, image=controller.bg_image, anchor="nw")

        # Ekran genişlik/yükseklik
        sw, sh = controller.winfo_screenwidth(), controller.winfo_screenheight()

        # Logo ortada
        logo_y = sh // 3
        canvas.create_image(sw // 2, logo_y, image=controller.logo_image, anchor="center")

        # Logo altına yazı (daha büyük + boşluk ayarlı)
        text_y = logo_y + controller.logo_image.height() // 2 + 60  # boşluk artırıldı
        canvas.create_text(
            sw // 2,
            text_y,
            text="Diyabet Takip Sistemine Hoşgeldiniz",
            font=("Arial", 32, "bold"),   # font büyütüldü
            fill="navy"
        )

        # Devam et butonu → yazının tam altına ortalanmış + daha büyük
        devam_buton_y = text_y + 80
        devam_btn = tk.Button(self,
                              text="Devam et",
                              font=("Arial", 16, "bold"),
                              bg="navy",
                              fg="white",
                              padx=20, pady=10,
                              command=lambda: controller.show_frame("LoginFrame"))
        devam_btn.place(x=sw // 2, y=devam_buton_y, anchor="n")


# -----------------------------------------------------
# Giriş Ekranı
# -----------------------------------------------------
class LoginFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan etiketi
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Giriş formu
        frm = tk.Frame(self, bg="white", bd=2, relief="ridge")
        frm.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frm, text="TC Kimlik No:", bg="white", font=("Arial",12))\
            .grid(row=0, column=0, sticky="e", pady=5, padx=5)
        self.tc_entry = tk.Entry(frm, font=("Arial",12), width=30)
        self.tc_entry.grid(row=0, column=1, pady=5, padx=5)

        tk.Label(frm, text="Şifre:", bg="white", font=("Arial",12))\
            .grid(row=1, column=0, sticky="e", pady=5, padx=5)
        self.pw_entry = tk.Entry(frm, font=("Arial",12), width=30, show="*")
        self.pw_entry.grid(row=1, column=1, pady=5, padx=5)

        btnf = tk.Frame(frm, bg="white")
        btnf.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btnf, text="Giriş Yap", width=12, command=self.login).pack(side="left", padx=5)
        tk.Button(btnf, text="Çıkış", width=12, command=controller.destroy).pack(side="right", padx=5)

    def login(self):
        tc = self.tc_entry.get().strip()
        pw = self.pw_entry.get().strip()

        # TC doğrulama
        if not (tc.isdigit() and len(tc) == 11):
            messagebox.showerror("Geçersiz TC", "TC kimlik numarası 11 haneli olmalı.")
            return
        if not pw:
            messagebox.showwarning("Eksik Bilgi", "Lütfen şifrenizi girin.")
            return

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()

            # Doktor mu?
            cur.execute(
                "SELECT sifre, isim FROM doktor WHERE kullanici_adi=%s",
                (tc,)
            )
            row = cur.fetchone()
            if row:
                stored_hash = row[0]
                # Eğer hash string olarak geldiyse bytes'a çevir
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')
                if bcrypt.checkpw(pw.encode('utf-8'), stored_hash):
                    self.controller.current_role      = "doctor"
                    self.controller.current_user_tc   = tc
                    self.controller.current_user_name = row[1]
                    cur.close(); conn.close()
                    self.controller.show_frame("DoctorFrame")
                    return

            # Hasta mı?
            cur.execute(
                "SELECT sifre, isim FROM hasta WHERE kullanici_adi=%s",
                (tc,)
            )
            row = cur.fetchone()
            if row:
                stored_hash = row[0]
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')
                if bcrypt.checkpw(pw.encode('utf-8'), stored_hash):
                    self.controller.current_role      = "patient"
                    self.controller.current_user_tc   = tc
                    self.controller.current_user_name = row[1]
                    cur.close(); conn.close()
                    self.controller.show_frame("PatientFrame")
                    return

            cur.close(); conn.close()
            messagebox.showerror("Giriş Hatası", "TC veya şifre hatalı.")
        except mysql.connector.Error as e:
            messagebox.showerror("DB Hatası", e)

# -----------------------------------------------------
# Doktor Paneli
# -----------------------------------------------------
class DoctorFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Üst çerçeve: başlık + fotoğraf
        top_frame = tk.Frame(self, bg="white")
        top_frame.pack(pady=15)

        # Doktor fotoğrafı (boş label, sonra doldurulacak)
        self.photo_label = tk.Label(top_frame, bg="white")
        self.photo_label.pack(side="left", padx=10)

        # Başlık
        self.header = tk.Label(top_frame, font=("Arial", 18, "bold"), bg="white")
        self.header.pack(side="left", padx=10)

        # Hasta seçimi
        self.patient_var = tk.StringVar()
        tk.Label(self, text="Hasta:", font=("Arial", 12), bg="white").pack(pady=5)
        self.patient_menu = tk.OptionMenu(self, self.patient_var, "")
        self.patient_menu.pack()

        # İşlem butonları
        btn_container = tk.Frame(self, bg="white")
        btn_container.pack(pady=20)

        buttons = [
            ("Hasta Tanımlama", "NewPatientFrame"),
            ("Kan Şekeri Seviyesi", "DoctorOlcumFrame"),
            ("Hastalık Belirti",  "SymptomFrame"),
            ("Egzersiz Öneri",  "EgzersizOnerFrame"),
            ("Beslenme Planı",     "DiyetPlanFrame"),
            ("Veri Görüntüle",  "DataViewFrame"),
            ("Filtrele",        "DoctorFilterFrame"),
            ("Grafikler",       "DoctorGraphFrame"),
            ("Uyarılar",        "UyariFrame"),
        ]
        for (label, frame_name) in buttons:
            tk.Button(
                btn_container,
                text=label,
                width=14,
                command=lambda f=frame_name: controller.show_frame(f)
            ).pack(side="left", padx=5)

        # Alt navigasyon
        nav = tk.Frame(self, bg="white")
        nav.pack(side="bottom", fill="x", pady=10)
        tk.Button(nav, text="Geri", command=controller.go_back).pack(side="left", padx=20)
        tk.Button(nav, text="Çıkış", command=controller.destroy).pack(side="right", padx=20)

    def tkraise(self, above=None):
        # Başlığı güncelle
        self.header.config(text=f"Hoşgeldiniz Dr. {self.controller.current_user_name}")

        # Fotoğraf yükle
        doctor_tc = self.controller.current_user_tc  # giriş yapan doktorun tc
        photo_path = self.get_doctor_photo_path(doctor_tc)
        if photo_path:
            try:
                img = Image.open(photo_path)
                img = img.resize((80, 80))  # Fotoğraf boyutu ayarla
                photo = ImageTk.PhotoImage(img)
                self.photo_label.config(image=photo)
                self.photo_label.image = photo  # Referans tut
            except Exception as e:
                print(f"Fotoğraf yüklenemedi: {e}")

        # Hasta listesini doldur
        menu = self.patient_menu["menu"]
        menu.delete(0, "end")
        for tc, isim in self.controller.get_my_patients():
            menu.add_command(
                label=f"{tc} – {isim}",
                command=lambda v=tc: self.patient_var.set(v)
            )
        patients = self.controller.get_my_patients()
        if patients:
            self.patient_var.set(patients[0][0])

        super().tkraise(above)

    def get_doctor_photo_path(self, tc):
        # MySQL'den doktorun fotoğraf yolunu çek
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT resim FROM doktor WHERE kullanici_adi = %s", (tc,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            print(f"MySQL Hata: {e}")
            return None


# -----------------------------------------------------
# Yeni Hasta Kayıt
# -----------------------------------------------------
class NewPatientFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Yeni Hasta Kayıt",
                 font=("Arial", 16, "bold"), bg="white").pack(pady=10)
        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        # Label isimleri (şifre çıkarıldı!)
        labels = ["TC", "Resim", "E-posta",
                  "Doğum (DD.MM.YYYY)", "Cinsiyet", "İsim", "Şehir"]
        self.entries = {}

        for i, lbl in enumerate(labels):
            tk.Label(frm, text=lbl + ":", bg="white").grid(
                row=i, column=0, sticky="e", pady=2, padx=5
            )

            if lbl == "Resim":
                resim_frame = tk.Frame(frm, bg="white")
                resim_frame.grid(row=i, column=1, pady=2, padx=5, sticky="w")
                resim_entry = tk.Entry(resim_frame, width=25)
                resim_entry.pack(side="left")
                self.entries[lbl] = resim_entry
                sec_button = tk.Button(
                    resim_frame,
                    text="Seç",
                    command=lambda e=resim_entry: self.select_file(e)
                )
                sec_button.pack(side="left", padx=5)
            else:
                e = tk.Entry(frm, width=30)
                e.grid(row=i, column=1, pady=2, padx=5)
                self.entries[lbl] = e

        # Butonlar
        bf = tk.Frame(self, bg="white")
        bf.pack(pady=15)
        tk.Button(bf, text="Kaydet", width=12,
                  command=self.save).pack(side="left", padx=5)
        tk.Button(bf, text="Geri", width=12,
                  command=controller.go_back).pack(side="right", padx=5)

    def select_file(self, entry_widget):
        file_path = filedialog.askopenfilename(
            title="Resim Seç",
            filetypes=[("Resim Dosyaları", "*.jpg *.jpeg *.png *.bmp *.gif"), ("Tüm Dosyalar", "*.*")]
        )
        if file_path:
            normalized_path = file_path.replace("\\", "/")
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, normalized_path)

    def save(self):
        vals = [e.get().strip() for e in self.entries.values()]
        if any(not v for v in vals):
            messagebox.showwarning("Eksik Bilgi", "Lütfen tüm alanları doldurun.")
            return

        tc, img, em, dob_input, gn, ad, se = vals

        # TC doğrulama
        if not (tc.isdigit() and len(tc) == 11):
            messagebox.showerror("Geçersiz TC",
                                 "TC kimlik numarası 11 haneli olmalı ve sadece rakam içermelidir.")
            return

        # Otomatik 6 haneli şifre oluştur
        random_password = "{:06d}".format(random.randint(0, 999999))
        salt = bcrypt.gensalt(rounds=HASH_ROUNDS)
        pw_hash = bcrypt.hashpw(random_password.encode(), salt)

        try:
            # Doğum tarihini parse edip MySQL formatına çevir
            dt_dob = datetime.strptime(dob_input, "%d.%m.%Y")
            dob_mysql = dt_dob.strftime("%Y-%m-%d")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO hasta "
                "(kullanici_adi, sifre, resim, email, dogum_tarihi, cinsiyet, isim, sehir, doktor_tc) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (tc, pw_hash, img, em, dob_mysql, gn, ad, se, self.controller.current_user_tc)
            )
            conn.commit()
            cur.close()
            conn.close()

            # E-posta gönder
            send_email(em, tc, random_password, self.controller.current_user_name)
            messagebox.showinfo("Başarılı", "Hasta kaydedildi.\nŞifre e-posta ile gönderildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Doğum Tarihi",
                "Lütfen Doğum için DD.MM.YYYY formatını kullanın."
            )
        except mysql.connector.Error as e:
            messagebox.showerror("Hata", str(e))




# -----------------------------------------------------
# Doktor için Ölçüm Girişi
# -----------------------------------------------------
class DoctorOlcumFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Doktor — Yeni Ölçüm Girişi",
                 font=("Arial", 16, "bold"), bg="white").pack(pady=10)

        # Form
        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        # Hasta TC (DoctorFrame’den geliyor)
        tk.Label(frm, text="Hasta TC:", bg="white").grid(row=0, column=0, sticky="e", pady=2, padx=5)
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0, column=1, sticky="w", pady=2)

        # Tarih/Saat
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white").grid(row=1, column=0, sticky="e", pady=2, padx=5)
        self.tarih = tk.Entry(frm, width=25)
        self.tarih.grid(row=1, column=1, pady=2)

        # Seviye
        tk.Label(frm, text="Seviye (mg/dL):", bg="white").grid(row=2, column=0, sticky="e", pady=2, padx=5)
        self.seviye = tk.Entry(frm, width=25)
        self.seviye.grid(row=2, column=1, pady=2)

        # Butonlar
        bf = tk.Frame(self, bg="white")
        bf.pack(pady=15)
        tk.Button(bf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(bf, text="Geri", command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        # DoctorFrame’den seçili hastayı al
        sec = self.controller.frames["DoctorFrame"].patient_var.get()
        self.tc.config(text=sec)
        # Tarih/Saat alanını otomatik olarak şimdiki zamanla doldur
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, now)
        super().tkraise(above)

    def save(self):
        tc = self.tc.cget("text").strip()
        tarih_input = self.tarih.get().strip()
        seviye_input = self.seviye.get().strip()

        try:
            # Tarihi dönüştür
            dt = datetime.strptime(tarih_input, "%d.%m.%Y %H:%M:%S")
            tarih_mysql = dt.strftime("%Y-%m-%d %H:%M:%S")
            seviye = int(seviye_input)

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Veriyi doktor_kan_olcum tablosuna kaydet
            cur.execute(
                "INSERT INTO doktor_kan_olcum (hasta_tc, tarih_saat, seviye_mgdl) VALUES (%s, %s, %s)",
                (tc, tarih_mysql, seviye)
            )

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı", "Ölçüm başarıyla kaydedildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror(
                "Hata", "Tarih formatı veya seviye hatalı.\nTarih: DD.MM.YYYY HH:MM:SS\nSeviye: Sayısal değer olmalı."
            )
        except Exception as e:
            messagebox.showerror("Hata", f"Veri kaydedilirken hata oluştu:\n{e}")

# -----------------------------------------------------
# Doktor için Belirti Girişi
# -----------------------------------------------------
class SymptomFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Doktor — Belirti Girişi",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)
        frm = tk.Frame(self, bg="white"); frm.pack(pady=5)

        # Hasta TC
        tk.Label(frm, text="Hasta TC:", bg="white") \
            .grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0, column=1, sticky="w", pady=2)

        # Tarih/Saat (DD.MM.YYYY HH:MM:SS)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white") \
            .grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.tarih = tk.Entry(frm, font=("Arial",12), width=25)
        self.tarih.grid(row=1, column=1, pady=2)
        # Örnek placeholder (isteğe bağlı)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        # Semptom türleri
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, tur FROM semptom_turleri")
        self.semptom_turleri = cur.fetchall()
        cur.close(); conn.close()

        semptom_isimler = [t for _, t in self.semptom_turleri]
        tk.Label(frm, text="Semptom Türü:", bg="white") \
            .grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self.semptom_var = tk.StringVar(value=semptom_isimler[0])
        tk.OptionMenu(frm, self.semptom_var, *semptom_isimler).grid(row=2, column=1, pady=2)

        # Açıklama
        tk.Label(frm, text="Açıklama:", bg="white") \
            .grid(row=3, column=0, sticky="ne", padx=5, pady=2)
        self.aciklama = tk.Text(frm, width=30, height=4)
        self.aciklama.grid(row=3, column=1, pady=2)

        # Butonlar
        btnf = tk.Frame(self, bg="white"); btnf.pack(pady=15)
        tk.Button(btnf, text="Kaydet", width=12, command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri",   width=12, command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        # Güncel hastayı al
        self.tc.config(text=self.controller.frames["DoctorFrame"].patient_var.get())
        super().tkraise(above)

    def save(self):
        tc = self.tc.cget("text")
        tr_input = self.tarih.get().strip()
        secili = self.semptom_var.get()
        acik = self.aciklama.get("1.0","end").strip()
        sem_id = next(i for i,t in self.semptom_turleri if t == secili)

        try:
            # Tarih parse: DD.MM.YYYY HH:MM:SS
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                     .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt.strftime("%Y-%m-%d %H:%M:%S")  # DB’ye bu formatı yolluyoruz

            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO tbl_semptom "
                "(hasta_tc, tarih_saat, semptom_tur_id, aciklama) "
                "VALUES (%s,%s,%s,%s)",
                (tc, tr, sem_id, acik)
            )
            conn.commit(); cur.close(); conn.close()

            messagebox.showinfo("Başarılı","Belirti kaydedildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
        except Exception as e:
            messagebox.showerror("Hata", e)

# -----------------------------------------------------
# Doktor için Egzersiz Önerisi
# -----------------------------------------------------
class EgzersizOnerFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Doktor — Egzersiz Önerisi",
                 font=("Arial", 16, "bold"), bg="white").pack(pady=10)

        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        # Hasta TC
        tk.Label(frm, text="Hasta TC:", bg="white")\
            .grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0, column=1, sticky="w", pady=4)

        # Tarih/Saat
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white")\
            .grid(row=1, column=0, sticky="e", padx=5, pady=4)
        self.tarih = tk.Entry(frm, font=("Arial", 12), width=25)
        self.tarih.grid(row=1, column=1, pady=4)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        # Bilgilendirme yazısı (başlangıçta boş)
        self.info_label = tk.Label(frm, text="", font=("Arial", 10), bg="white")
        self.info_label.grid(row=2, column=0, columnspan=2, pady=(10, 0))

        # Egzersiz türü
        tk.Label(frm, text="Egzersiz Türü:", bg="white")\
            .grid(row=3, column=0, sticky="e", padx=5, pady=4)
        self.egz_var = tk.StringVar()
        self.egz_menu = tk.OptionMenu(frm, self.egz_var, "")
        self.egz_menu.grid(row=3, column=1, pady=4, sticky="w")

        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=15)
        tk.Button(btnf, text="Kaydet", width=12, command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri", width=12, command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        self.tc.config(text=self.controller.frames["DoctorFrame"].patient_var.get())
        self.load_exercise_recommendation()
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        super().tkraise(above)

    def load_exercise_recommendation(self):
        try:
            tc = self.tc.cget("text")
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Son glukoz seviyesi
            cur.execute(
                "SELECT seviye_mgdl FROM doktor_kan_olcum "
                "WHERE hasta_tc=%s ORDER BY tarih_saat DESC LIMIT 1",
                (tc,)
            )
            row = cur.fetchone()
            seviye = row[0] if row else None

            # Tüm semptomları çek
            cur.execute("""
                SELECT st.tur
                FROM tbl_semptom s
                JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                WHERE s.hasta_tc = %s
            """, (tc,))
            semptom_rows = cur.fetchall()
            semptoms = [t for (t,) in semptom_rows]

            # Egzersiz türlerini çek
            cur.execute("SELECT id, tur FROM egzersiz_turleri")
            self.egz_turleri = cur.fetchall()
            all_exercises = [tur for _, tur in self.egz_turleri]

            # Öneri hesapla
            exercise = None
            if seviye is not None:
                _, exercise = get_recommendation(seviye, semptoms)

            # Bilgilendirme yazısını güncelle
            if exercise:
                self.info_label.config(text=f"Sistem tarafından {exercise} öneriliyor: ")
            else:
                self.info_label.config(text="")

            # Menüye ekle
            menu = self.egz_menu["menu"]
            menu.delete(0, "end")
            for val in all_exercises:
                menu.add_command(label=val, command=lambda v=val: self.egz_var.set(v))

            # Varsayılan seçim
            if exercise in all_exercises:
                self.egz_var.set(exercise)
            elif all_exercises:
                self.egz_var.set(all_exercises[0])

            cur.close()
            conn.close()

        except Exception as e:
            print(f"load_exercise_recommendation hatası: {e}")

    def save(self):
        tc = self.tc.cget("text")
        tr_input = self.tarih.get().strip()
        egz_tur = self.egz_var.get()

        try:
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S")\
                       .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()

            egz_id = next(i for i, tur in self.egz_turleri if tur == egz_tur)

            cur.execute(
                "INSERT INTO tbl_egzersiz_oneri (hasta_tc, tarih_saat, egzersiz_tur_id) "
                "VALUES (%s, %s, %s)",
                (tc, tr, egz_id)
            )

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı", "Egzersiz önerisi kaydedildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror("Geçersiz Tarih", "Lütfen DD.MM.YYYY HH:MM:SS formatında tarih girin.")
        except Exception as e:
            messagebox.showerror("Hata", e)
# -----------------------------------------------------
# Doktor için Diyet Planı
# -----------------------------------------------------
class DiyetPlanFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Doktor — Diyet Planı",
                 font=("Arial", 16, "bold"), bg="white").pack(pady=10)

        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        tk.Label(frm, text="Hasta TC:", bg="white")\
            .grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0, column=1, sticky="w", pady=4)

        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white")\
            .grid(row=1, column=0, sticky="e", padx=5, pady=4)
        self.tarih = tk.Entry(frm, font=("Arial", 12), width=25)
        self.tarih.grid(row=1, column=1, pady=4)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        # Bilgilendirme yazısı başlangıçta boş
        self.info_label = tk.Label(frm, text="", font=("Arial", 10), bg="white")
        self.info_label.grid(row=2, column=0, columnspan=2, pady=(10, 0))

        tk.Label(frm, text="Diyet Türü:", bg="white")\
            .grid(row=3, column=0, sticky="e", padx=5, pady=4)
        self.diyet_var = tk.StringVar()
        self.diyet_menu = tk.OptionMenu(frm, self.diyet_var, "")
        self.diyet_menu.grid(row=3, column=1, pady=4, sticky="w")

        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=15)
        tk.Button(btnf, text="Kaydet", width=12, command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri", width=12, command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        self.tc.config(text=self.controller.frames["DoctorFrame"].patient_var.get())
        self.load_diet_recommendation()
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        super().tkraise(above)

    def load_diet_recommendation(self):
        try:
            tc = self.tc.cget("text")
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Son glukoz seviyesi
            cur.execute(
                "SELECT seviye_mgdl FROM doktor_kan_olcum "
                "WHERE hasta_tc=%s ORDER BY tarih_saat DESC LIMIT 1",
                (tc,)
            )
            row = cur.fetchone()
            seviye = row[0] if row else None

            # Tüm semptomları çek
            cur.execute("""
                SELECT st.tur
                FROM tbl_semptom s
                JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                WHERE s.hasta_tc = %s
            """, (tc,))
            semptom_rows = cur.fetchall()
            semptoms = [t for (t,) in semptom_rows]

            # Diyet türlerini çek
            cur.execute("SELECT id, tur FROM diyet_turleri")
            self.diyet_turleri = cur.fetchall()
            all_diets = [tur for _, tur in self.diyet_turleri]

            # Öneri hesapla
            diet = None
            if seviye is not None:
                diet, _ = get_recommendation(seviye, semptoms)

            # Bilgilendirme yazısını güncelle
            if diet:
                self.info_label.config(text=f"Sistem tarafından {diet} öneriliyor.")
            else:
                self.info_label.config(text="")

            # Menüye ekle
            menu = self.diyet_menu["menu"]
            menu.delete(0, "end")
            for val in all_diets:
                menu.add_command(label=val, command=lambda v=val: self.diyet_var.set(v))

            # Varsayılan seçim
            if diet in all_diets:
                self.diyet_var.set(diet)
            elif all_diets:
                self.diyet_var.set(all_diets[0])

            cur.close()
            conn.close()

        except Exception as e:
            print(f"load_diet_recommendation hatası: {e}")

    def save(self):
        tc = self.tc.cget("text")
        tr_input = self.tarih.get().strip()
        diyet = self.diyet_var.get()

        try:
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S")\
                       .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()

            diyet_id = next(i for i, tur in self.diyet_turleri if tur == diyet)

            cur.execute(
                "INSERT INTO tbl_diyet_plani (hasta_tc, tarih_saat, diyet_tur_id) "
                "VALUES (%s, %s, %s)",
                (tc, tr, diyet_id)
            )

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı", "Diyet planı kaydedildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror("Geçersiz Tarih", "Lütfen DD.MM.YYYY HH:MM:SS formatında tarih girin.")
        except Exception as e:
            messagebox.showerror("Hata", e)


# -----------------------------------------------------
# Doktor için Veri Görüntüleme
# -----------------------------------------------------
class DataViewFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Doktor — Veri Görüntüle",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)

        frm = tk.Frame(self, bg="white"); frm.pack(pady=5)
        tk.Label(frm, text="Tablo Seçin:", bg="white").grid(row=0,column=0,sticky="e")
        self.tbl_var = tk.StringVar(value="tbl_olcum")
        opts = ['tbl_olcum','tbl_semptom','tbl_egzersiz_oneri','tbl_diyet_plani']
        tk.OptionMenu(frm, self.tbl_var, *opts).grid(row=0,column=1,pady=2)

        bf = tk.Frame(self, bg="white"); bf.pack(pady=10)
        tk.Button(bf, text="Göster", command=self.show_data).pack(side="left", padx=5)
        tk.Button(bf, text="Geri",    command=controller.go_back).pack(side="right", padx=5)

        self.text = tk.Text(self, width=80, height=20)
        self.text.pack(pady=10)

    def show_data(self):
        tbl = self.tbl_var.get()
        tc  = self.controller.frames["DoctorFrame"].patient_var.get()
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(f"SELECT * FROM {tbl} WHERE hasta_tc=%s ORDER BY tarih_saat DESC LIMIT 20",(tc,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            cur.close(); conn.close()

            self.text.delete("1.0","end")
            self.text.insert("end", "\t".join(cols)+"\n")
            self.text.insert("end", "-"*60+"\n")
            for r in rows:
                self.text.insert("end"," | ".join(str(x) for x in r)+"\n")

        except Exception as e:
            messagebox.showerror("Hata", e)

# -----------------------------------------------------
# Hasta Paneli
# -----------------------------------------------------
class PatientFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Üst çerçeve: fotoğraf + başlık
        top_frame = tk.Frame(self, bg="white")
        top_frame.pack(pady=15)

        # Hasta fotoğrafı (boş label, sonra doldurulacak)
        self.photo_label = tk.Label(top_frame, bg="white")
        self.photo_label.pack(side="left", padx=10)

        # Başlık (isim)
        self.header = tk.Label(top_frame, font=("Arial", 18, "bold"), bg="white")
        self.header.pack(side="left", padx=10)

        # Açıklama
        info = (
            "Buradan günlük kan şekeri ölçümü, egzersiz takibi, "
            "diyet takibi ve belirti takibini yapabilirsiniz."
        )
        tk.Label(
            self,
            text=info,
            wraplength=700,
            font=("Arial", 12),
            bg="white"
        ).pack(pady=10)

        # İşlem butonları
        btn_container = tk.Frame(self, bg="white")
        btn_container.pack(pady=20)

        buttons = [
            ("Kan Şekeri Girişi",  "OlcumEntryFrame"),
            ("Egzersiz Takip",     "EgzersizTakipFrame"),
            ("Diyet Takip",        "DiyetTakipFrame"),
            ("Belirti Takip",      "PatientSymptomEntryFrame"),
            ("Günlük Ortalama",    "PatientGraphFrame"),
            ("İnsülin Takip",      "InsulinViewFrame"),
        ]
        for (label, frame_name) in buttons:
            tk.Button(
                btn_container,
                text=label,
                width=16,
                command=lambda f=frame_name: controller.show_frame(f)
            ).pack(side="left", padx=5)

        # Alt navigasyon
        nav = tk.Frame(self, bg="white")
        nav.pack(side="bottom", fill="x", pady=10)
        tk.Button(nav, text="Geri", command=controller.go_back).pack(side="left", padx=20)
        tk.Button(nav, text="Çıkış", command=controller.destroy).pack(side="right", padx=20)

    def tkraise(self, above=None):
        # Başlığı güncelle
        self.header.config(text=f"{self.controller.current_user_name}, hoşgeldiniz.")

        # Fotoğraf yükle
        patient_tc = self.controller.current_user_tc  # giriş yapan hastanın tc
        photo_path = self.get_patient_photo_path(patient_tc)
        if photo_path:
            try:
                img = Image.open(photo_path)
                img = img.resize((80, 80))  # Fotoğraf boyutu ayarla
                photo = ImageTk.PhotoImage(img)
                self.photo_label.config(image=photo)
                self.photo_label.image = photo  # Referans tut
            except Exception as e:
                print(f"Fotoğraf yüklenemedi: {e}")

        super().tkraise(above)

    def get_patient_photo_path(self, tc):
        # MySQL'den hastanın fotoğraf yolunu çek
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT resim FROM hasta WHERE kullanici_adi = %s", (tc,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            print(f"MySQL Hata: {e}")
            return None


# -----------------------------------------------------
# Hasta — Kan Şekeri Girişi
# -----------------------------------------------------
class OlcumEntryFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Kan Şekeri Girişi",
                 font=("Arial", 18, "bold"),
                 bg="white").pack(pady=(30, 10))

        # Form çerçevesi
        form = tk.Frame(self, bg="white", bd=1, relief="solid")
        form.pack(pady=10, padx=20)

        # Grid ile hizalanmış form satırları
        labels = ["Tarih/Saat (DD.MM.YYYY HH:MM:SS):", "Seviye (mg/dL):", "Tür:"]
        for i, text in enumerate(labels):
            tk.Label(form, text=text, bg="white",
                     font=("Arial", 12)).grid(row=i, column=0,
                                              sticky="e", padx=10, pady=8)

        # Girdi alanları
        self.tarih = tk.Entry(form, font=("Arial", 12), width=25)
        self.tarih.grid(row=0, column=1, padx=10, pady=8)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        gs_btn = tk.Button(form, text="Gün Sonu", command=self.end_of_day)
        gs_btn.grid(row=0, column=2, padx=10, pady=8)

        self.seviye = tk.Entry(form, font=("Arial", 12), width=25)
        self.seviye.grid(row=1, column=1, padx=10, pady=8)

        self.tur_var = tk.StringVar(value="Sabah")
        tk.OptionMenu(form, self.tur_var,
                      *['Sabah', 'Öğle', 'İkindi', 'Akşam', 'Gece']) \
            .grid(row=2, column=1, padx=10, pady=8, sticky="w")

        # Butonlar
        btn_frame = tk.Frame(self, bg="white")
        btn_frame.pack(pady=(20, 10))
        tk.Button(btn_frame, text="Kaydet", width=12,
                  command=self.save).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Geri", width=12,
                  command=controller.go_back).pack(side="left", padx=5)

        # Mesajları gösterecek alan
        self.msg_area = tk.Message(
            self,
            text="",
            width=600,
            bg="white",
            font=("Arial", 12),
            justify="left"
        )
        self.msg_area.pack(pady=(10, 0), padx=20)

    def save(self):
        # Mesaj alanını temizle
        self.msg_area.config(text="")
        messages = []

        tc = self.controller.current_user_tc
        tr_input = self.tarih.get().strip()  # "DD.MM.YYYY HH:MM:SS"
        try:
            sv = int(self.seviye.get())
        except ValueError:
            messagebox.showerror("Hata", "Seviye sayısal olmalı.")
            return
        tur = self.tur_var.get()

        try:
            # Tarih parse & MySQL format
            dt_local = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                       .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr_mysql = dt_local.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor(buffered=True)

            # Aynı güne aynı türden tekrar girilmesini engelle
            cur.execute(
                "SELECT 1 FROM tbl_olcum "
                "WHERE hasta_tc=%s AND tur=%s AND DATE(tarih_saat)=DATE(%s)",
                (tc, tur, tr_mysql)
            )
            if cur.fetchone():
                messages.append(f"Bugün için zaten “{tur}” ölçümü kaydedilmiş, tekrar eklenemez.")
                self.msg_area.config(text="\n".join(messages))
                cur.close()
                conn.close()
                return

            # 1) Ölçümü tabloya kaydet
            cur.execute(
                "INSERT INTO tbl_olcum (hasta_tc, tarih_saat, seviye_mgdl, tur) "
                "VALUES (%s, %s, %s, %s)",
                (tc, tr_mysql, sv, tur)
            )

            # 2) Ölçüm seviyesi uyarısı (Normal aralık = 70–110 hariç)
            if sv < 70:
                durum, uyarı_tipi, mesaj = (
                    "Hipoglisemi Riski",
                    "Acil Uyarı",
                    "Hastanın kan şekeri seviyesi 70 mg/dL'nin altına düştü. Hipoglisemi riski! Hızlı müdahale gerekebilir."
                )
            elif sv <= 110:
                # Normal aralıkta -> uyarı yok, tabloya yazma
                durum = uyarı_tipi = mesaj = None
            elif sv <= 150:
                durum, uyarı_tipi, mesaj = (
                    "Orta Yüksek Seviye",
                    "Takip Uyarısı",
                    "Hastanın kan şekeri 111–150 mg/dL arasında. Durum izlenmeli."
                )
            elif sv <= 200:
                durum, uyarı_tipi, mesaj = (
                    "Yüksek Seviye",
                    "İzleme Uyarısı",
                    "Hastanın kan şekeri 151–200 mg/dL arasında. Diyabet kontrolü gerekli."
                )
            else:
                durum, uyarı_tipi, mesaj = (
                    "Çok Yüksek Seviye (Hiperglisemi)",
                    "Acil Müdahale Uyarısı",
                    "Hastanın kan şekeri 200 mg/dL'nin üzerinde. Hiperglisemi durumu. Acil müdahale gerekebilir."
                )

            if durum:
                cur.execute(
                    "INSERT INTO uyarilar (hasta_tc, tarih_saat, durum, uyarı_tipi, mesaj) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (tc, tr_mysql, durum, uyarı_tipi, mesaj)
                )

            # 2.5) Zaman aralığı kontrolü: yalnızca bu ölçüme ait uyarı
            start_new, end_new = VALID_WINDOWS[tur]
            if not (start_new <= dt_local.time() <= end_new):
                msg2 = "Ölçüm zamanı aralık dışında; ortalamaya dahil edilmeyecek."
                messages.append(msg2)

            # 3) Önceki öğünler eksikse bildir
            order = ['Sabah', 'Öğle', 'İkindi', 'Akşam', 'Gece']
            idx = order.index(tur)
            for prev in order[:idx]:
                cur.execute(
                    "SELECT 1 FROM tbl_olcum "
                    "WHERE hasta_tc=%s AND DATE(tarih_saat)=DATE(%s) AND tur=%s",
                    (tc, tr_mysql, prev)
                )
                if not cur.fetchone():
                    msg_prev = f"{prev} ölçümü eksik! Ortalama alınırken bu ölçüm hesaba katılmadı."
                    cur.execute(
                        "INSERT INTO uyarilar (hasta_tc, tarih_saat, mesaj, durum, uyarı_tipi) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (tc, tr_mysql, msg_prev, "Ölçüm Eksik", "Eksik Ölçüm Uyarısı")
                    )
                    messages.append(msg_prev)

            # 4) Bu günün ölçümlerini çek, sadece pencere içindekileri al
            cur.execute(
                "SELECT tarih_saat, seviye_mgdl, tur "
                "FROM tbl_olcum "
                "WHERE hasta_tc=%s AND DATE(tarih_saat)=DATE(%s)",
                (tc, tr_mysql)
            )
            rows = cur.fetchall()
            valid = []
            for ts, lvl, ttype in rows:
                s, e = VALID_WINDOWS[ttype]
                if s <= ts.time() <= e:
                    valid.append(lvl)

            # 5) Yetersiz veri kontrolü
            if len(valid) < 3:
                msg3 = "Yetersiz veri! Ortalama hesaplaması güvenilir değildir."
                messages.append(msg3)

            # 6) Ortalama + insülin dozu hesapla ve tabloya yaz, mesaj olarak ekle
            avg = (sum(valid) / len(valid)) if valid else 0.0
            if avg <= 110:
                dose, tip = 0, "Uyarı Yok"
                msg_ins = f"Ort. kan şekeri {avg:.1f} mg/dL → İnsülin önerisi yok."
            elif avg <= 150:
                dose, tip = 1, "Takip Uyarısı"
                msg_ins = f"Ort. kan şekeri {avg:.1f} mg/dL → 1 ml insülin öneriliyor."
            elif avg <= 200:
                dose, tip = 2, "İzleme Uyarısı"
                msg_ins = f"Ort. kan şekeri {avg:.1f} mg/dL → 2 ml insülin öneriliyor."
            else:
                dose, tip = 3, "Acil Müdahale Uyarısı"
                msg_ins = f"Ort. kan şekeri {avg:.1f} mg/dL → 3 ml insülin öneriliyor."

            cur.execute(
                "INSERT INTO tbl_insulin (hasta_tc, tarih_saat, birim_u) VALUES (%s, %s, %s)",
                (tc, tr_mysql, dose)
            )
            messages.append(msg_ins)

            # 7) Commit & sonuçları ekranda göster
            conn.commit()
            cur.close()
            conn.close()

            # Metin alanına tüm mesajları bir arada bas
            self.msg_area.config(text="\n".join(messages))

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
        except Exception as e:
            messagebox.showerror("Hata", str(e))

    def end_of_day(self):
        tc = self.controller.current_user_tc
        tr_input = self.tarih.get().strip()
        # Tarihi MySQL formatına çevir
        dt_local = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                         .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
        tr_mysql = dt_local.strftime("%Y-%m-%d %H:%M:%S")

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        # O günkü toplam ölçüm sayısı
        cur.execute(
            "SELECT COUNT(*) FROM tbl_olcum WHERE hasta_tc=%s AND DATE(tarih_saat)=DATE(%s)",
            (tc, tr_mysql)
        )
        toplam = cur.fetchone()[0] or 0

        if toplam == 0:
            durum, uyarı_tipi, mesaj = (
                "Ölçüm Eksikliği (Hiç Giriş Yok)",
                "Ölçüm Eksik Uyarısı",
                "Hasta gün boyunca kan şekeri ölçümü yapmamıştır. Acil takip önerilir."
            )
        elif toplam < 3:
            durum, uyarı_tipi, mesaj = (
                "Ölçüm Eksikliği (3’ten Az Giriş)",
                "Ölçüm Yetersiz Uyarısı",
                "Hastanın günlük kan şekeri ölçüm sayısı yetersiz (<3). Durum izlenmelidir."
            )
        else:
            # 3 veya daha fazla ölçüm varsa uyarı oluşturma
            conn.close()
            messagebox.showinfo("Gün Sonu", "Bugün için yeterli ölçüm var, uyarı oluşturulmadı.")
            return

        # Uyarıyı tabloya kaydet
        cur.execute(
            "INSERT INTO uyarilar (hasta_tc, tarih_saat, durum, uyarı_tipi, mesaj) "
            "VALUES (%s, %s, %s, %s, %s)",
            (tc, tr_mysql, durum, uyarı_tipi, mesaj)
        )
        conn.commit()
        cur.close()
        conn.close()

        messagebox.showinfo("Gün Sonu Uyarısı", mesaj)

# -----------------------------------------------------
# Hasta — Egzersiz Uyum Takibi
# -----------------------------------------------------
class EgzersizTakipFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Egzersiz Uyum Takibi",
                 font=("Arial", 18, "bold"), bg="white")\
          .pack(pady=(15, 5))

        # Form
        form = tk.Frame(self, bg="white")
        form.pack(pady=5)

        tk.Label(form, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white")\
            .grid(row=0, column=0, sticky="e", padx=5)
        self.tarih = tk.Entry(form, width=25)
        self.tarih.grid(row=0, column=1, pady=2)
        # Başlangıçta otomatik şimdi ile doldur
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        self.yap_var = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text="Yapıldı", variable=self.yap_var, bg="white")\
            .grid(row=1, column=1, sticky="w")

        # Butonlar
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=10)
        tk.Button(btnf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri",   command=controller.go_back).pack(side="right", padx=5)

        # Doktor önerisi ve uyum özeti
        self.doktor_onerisi_label = tk.Label(self, text="", font=("Arial", 12), bg="white")
        self.doktor_onerisi_label.pack(pady=(10, 0))
        self.summary_label        = tk.Label(self, text="", font=("Arial", 12), bg="white")
        self.summary_label.pack(pady=(2, 10))

        # Uyum geçmişi tablosu
        cols = ("tarih", "durum")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=6)
        self.tree.heading("tarih", text="Tarih/Saat", anchor="center")
        self.tree.heading("durum",  text="Egzersiz Durumu", anchor="center")
        self.tree.column("tarih", width=200, anchor="center")
        self.tree.column("durum",  width=150, anchor="center")
        self.tree.pack(fill="x", padx=10, pady=(5,10))

    def tkraise(self, above=None):
        # Ekran her açıldığında tarihi güncelle
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, now)

        # Öneri ve tabloyu refresh et
        self.load_last_suggestion()
        self.populate_compliance()

        super().tkraise(above)

    def save(self):
        tc = self.controller.current_user_tc
        tr_text = self.tarih.get().strip()
        try:
            tr = datetime.strptime(tr_text, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            messagebox.showerror(
                "Hata",
                "Tarih/Saat formatı hatalı.\n"
                "Lütfen DD.MM.YYYY HH:MM:SS formatını kullanın."
            )
            return

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        # Aynı gün için kayıt kontrolü
        cur.execute(
            "SELECT 1 FROM tbl_egzersiz_takip "
            "WHERE hasta_tc=%s AND DATE(tarih_saat)=DATE(%s)",
            (tc, tr)
        )
        if cur.fetchone():
            messagebox.showerror("Hata", "Bu gün için zaten egzersiz kaydı yapılmış.")
            cur.close(); conn.close()
            return

        durum = "Egzersiz yapıldı" if self.yap_var.get() else "Egzersiz yapılmadı"
        cur.execute(
            """
            INSERT INTO tbl_egzersiz_takip
              (hasta_tc, tarih_saat, yapilan_egzersiz)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              yapilan_egzersiz = VALUES(yapilan_egzersiz)
            """,
            (tc, tr, durum)
        )
        conn.commit()
        cur.close(); conn.close()

        # Görünümü yenile ve giriş alanını şimdi ile doldur
        self.populate_compliance()
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, now)

    def load_last_suggestion(self):
        tc = self.controller.current_user_tc
        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute("""
            SELECT et.tur
            FROM tbl_egzersiz_oneri eo
            JOIN egzersiz_turleri et ON eo.egzersiz_tur_id = et.id
            WHERE eo.hasta_tc = %s
            ORDER BY eo.tarih_saat DESC
            LIMIT 1
        """, (tc,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if row:
            self.doktor_onerisi_label.config(text=f"Doktor Önerisi: {row[0]}")
        else:
            self.doktor_onerisi_label.config(text="Doktor Önerisi: Henüz yok")

    def populate_compliance(self):
        tc = self.controller.current_user_tc
        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        # Yüzde özeti
        cur.execute("SELECT COUNT(*) FROM tbl_egzersiz_takip WHERE hasta_tc=%s", (tc,))
        total = cur.fetchone()[0] or 0
        cur.execute("""
            SELECT COUNT(*) FROM tbl_egzersiz_takip
            WHERE hasta_tc=%s AND yapilan_egzersiz='Egzersiz yapıldı'
        """, (tc,))
        done = cur.fetchone()[0] or 0
        pct = (done/total*100) if total>0 else 0
        self.summary_label.config(
            text=f"Egzersiz Uyum: %{pct:.1f} yapıldı, %{100-pct:.1f} yapılmadı"
        )

        # Tabloyu güncelle
        for item in self.tree.get_children():
            self.tree.delete(item)
        cur.execute("""
            SELECT tarih_saat, yapilan_egzersiz
            FROM tbl_egzersiz_takip
            WHERE hasta_tc=%s
            ORDER BY tarih_saat DESC
        """, (tc,))
        for ts, durum in cur.fetchall():
            self.tree.insert(
                "", "end",
                values=(ts.strftime("%d.%m.%Y %H:%M:%S"), durum)
            )

        cur.close(); conn.close()


class DiyetTakipFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Diyet Uyum Takibi",
                 font=("Arial", 18, "bold"), bg="white")\
          .pack(pady=(15, 5))

        # Doktor önerisi
        self.doktor_onerisi_label = tk.Label(self, text="", font=("Arial", 12), bg="white")
        self.doktor_onerisi_label.pack(pady=(0, 10))

        # Form
        form = tk.Frame(self, bg="white")
        form.pack(pady=5)

        tk.Label(form, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white")\
          .grid(row=0, column=0, sticky="e", padx=5)
        self.tarih = tk.Entry(form, width=25)
        self.tarih.grid(row=0, column=1, pady=2)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        self.uyg_var = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text="Uygulandı", variable=self.uyg_var, bg="white")\
          .grid(row=1, column=1, sticky="w")

        # Butonlar
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=10)
        tk.Button(btnf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri",   command=controller.go_back).pack(side="right", padx=5)

        # Özet ve tablo
        self.summary_label = tk.Label(self, text="", font=("Arial", 12), bg="white")
        self.summary_label.pack(pady=(10,0))
        cols = ("tarih", "durum")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=6)
        self.tree.heading("tarih", text="Tarih/Saat", anchor="center")
        self.tree.heading("durum",  text="Diyet Durumu", anchor="center")
        self.tree.column("tarih", width=200, anchor="center")
        self.tree.column("durum",  width=150, anchor="center")
        self.tree.pack(fill="x", padx=10, pady=(5,10))

    def tkraise(self, above=None):
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, now)

        self.load_last_suggestion()
        self.populate_compliance()

        super().tkraise(above)

    def save(self):
        tc = self.controller.current_user_tc
        tr_text = self.tarih.get().strip()
        try:
            tr = datetime.strptime(tr_text, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            messagebox.showerror(
                "Hata",
                "Tarih/Saat formatı hatalı.\n"
                "Lütfen DD.MM.YYYY HH:MM:SS formatını kullanın."
            )
            return

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        # Aynı gün kontrolü
        cur.execute(
            "SELECT 1 FROM tbl_diyet_takip "
            "WHERE hasta_tc=%s AND DATE(tarih_saat)=DATE(%s)",
            (tc, tr)
        )
        if cur.fetchone():
            messagebox.showerror("Hata", "Bu gün için zaten diyet kaydı yapılmış.")
            cur.close(); conn.close()
            return

        durum = "Diyet uygulandı" if self.uyg_var.get() else "Diyet uygulanmadı"
        cur.execute(
            """
            INSERT INTO tbl_diyet_takip
              (hasta_tc, tarih_saat, uygulanan_diyet)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              uygulanan_diyet = VALUES(uygulanan_diyet)
            """,
            (tc, tr, durum)
        )
        conn.commit()
        cur.close(); conn.close()

        self.populate_compliance()
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, now)

    def load_last_suggestion(self):
        tc = self.controller.current_user_tc
        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute("""
            SELECT dt.tur
            FROM tbl_diyet_plani dp
            JOIN diyet_turleri dt ON dp.diyet_tur_id = dt.id
            WHERE dp.hasta_tc = %s
            ORDER BY dp.tarih_saat DESC
            LIMIT 1
        """, (tc,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if row:
            self.doktor_onerisi_label.config(text=f"Doktor Önerisi: {row[0]}")
        else:
            self.doktor_onerisi_label.config(text="Doktor Önerisi: Henüz yok")

    def populate_compliance(self):
        tc = self.controller.current_user_tc
        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM tbl_diyet_takip WHERE hasta_tc=%s", (tc,))
        total = cur.fetchone()[0] or 0
        cur.execute("""
            SELECT COUNT(*) FROM tbl_diyet_takip
            WHERE hasta_tc=%s AND uygulanan_diyet='Diyet uygulandı'
        """, (tc,))
        done = cur.fetchone()[0] or 0
        pct = (done/total*100) if total>0 else 0
        self.summary_label.config(
            text=f"Diyet Uyum: %{pct:.1f} yapıldı, %{100-pct:.1f} yapılmadı"
        )

        for item in self.tree.get_children():
            self.tree.delete(item)
        cur.execute("""
            SELECT tarih_saat, uygulanan_diyet
            FROM tbl_diyet_takip
            WHERE hasta_tc=%s
            ORDER BY tarih_saat DESC
        """, (tc,))
        for ts, durum in cur.fetchall():
            self.tree.insert(
                "", "end",
                values=(ts.strftime("%d.%m.%Y %H:%M:%S"), durum)
            )

        cur.close(); conn.close()

# -----------------------------------------------------
# Hasta — Belirti Görüntüle (basit liste)
# -----------------------------------------------------
class PatientSymptomEntryFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Doktor Teşhis Geçmişi",
                 font=("Arial", 16, "bold"), bg="white").pack(pady=15)

        # Scrollable frame yapısı (tüm geçmişi göstermek için)
        container = tk.Frame(self, bg="white")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(container, bg="white")
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="white")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Geri butonu
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=10)
        tk.Button(btnf, text="Geri", command=controller.go_back).pack()

    def tkraise(self, above=None):
        # Frame her açıldığında tüm teşhis geçmişini getir
        self.show_all_diagnoses()
        super().tkraise(above)

    def show_all_diagnoses(self):
        # Önce eski listeyi temizle
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        try:
            tc = self.controller.current_user_tc
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Tüm teşhis kayıtlarını çek (en son en üstte olsun)
            cur.execute("""
                SELECT s.tarih_saat, t.tur, s.aciklama
                FROM tbl_semptom s
                JOIN semptom_turleri t ON s.semptom_tur_id = t.id
                WHERE s.hasta_tc = %s
                ORDER BY s.tarih_saat DESC
            """, (tc,))
            results = cur.fetchall()
            cur.close()
            conn.close()

            if results:
                for idx, (tarih_saat, semptom_ismi, aciklama) in enumerate(results, 1):
                    info_text = f"{idx}) Doktorunuz {tarih_saat} zamanında {semptom_ismi} belirtisi teşhisi koymuştur."
                    aciklama_text = f"    Doktorunuzun açıklaması: {aciklama}"

                    tk.Label(self.scrollable_frame, text=info_text, 
                             font=("Arial", 12), bg="white", anchor="w", justify="left", wraplength=750)\
                        .pack(anchor="w", pady=(5, 0))

                    tk.Label(self.scrollable_frame, text=aciklama_text,
                             font=("Arial", 11, "italic"), bg="white", anchor="w", justify="left", wraplength=750)\
                        .pack(anchor="w", pady=(0, 10))
            else:
                tk.Label(self.scrollable_frame,
                         text="Doktorunuz tarafından henüz teşhis konmamıştır.",
                         font=("Arial", 12), bg="white").pack(pady=10)

        except Exception as e:
            tk.Label(self.scrollable_frame,
                     text="Teşhis bilgileri alınamadı.",
                     font=("Arial", 12), bg="white").pack(pady=10)
            print(f"Hata: {e}")


class DoctorFilterFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Doktor — Hastaları Filtrele", font=("Arial",16,"bold")).pack(pady=10)

        frm = tk.Frame(self)
        frm.pack(pady=5)

        # Min / Max kan seviyesi
        tk.Label(frm, text="Min Seviye (mg/dL):").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.min_entry = tk.Entry(frm, width=12)
        self.min_entry.grid(row=0, column=1, pady=2, sticky="w")

        tk.Label(frm, text="Max Seviye (mg/dL):").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.max_entry = tk.Entry(frm, width=12)
        self.max_entry.grid(row=1, column=1, pady=2, sticky="w")

        # Belirti seçimi
        tk.Label(frm, text="Belirti:").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.symptom_var = tk.StringVar(value="")
        symptoms = [""] + self._load_symptoms()
        self.symptom_menu = tk.OptionMenu(frm, self.symptom_var, *symptoms)
        self.symptom_menu.config(width=15)
        self.symptom_menu.grid(row=2, column=1, pady=2, sticky="w")

        # Filtrele butonu
        tk.Button(frm, text="Filtrele", command=self.filter).grid(row=3, column=0, columnspan=2, pady=10)

        # Geri butonu
        tk.Button(self, text="Geri", command=controller.go_back).pack(side="bottom", pady=5)

        # Sonuçları göstermek için Treeview
        cols = ("tc", "isim", "tarih", "tip", "deger")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=15)
        for c, w in zip(cols, [120, 150, 160, 100, 100]):
            self.tree.heading(c, text=c.upper(), anchor="center")
            self.tree.column(c, anchor="center", width=w)
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

    def _load_symptoms(self):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("SELECT tur FROM semptom_turleri ORDER BY tur")
            syms = [row[0] for row in cur.fetchall()]
            cur.close(); conn.close()
            return syms
        except:
            return []

    def filter(self):
        # Tabloyu temizle
        for item in self.tree.get_children():
            self.tree.delete(item)

        tc_doc = self.controller.current_user_tc
        min_v = self.min_entry.get().strip()
        max_v = self.max_entry.get().strip()
        symptom = self.symptom_var.get().strip()

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        # 1) Eğer hiçbir filtre girilmediyse → tüm hastalara ait olcum & semptom
        if not (min_v or max_v or symptom):
            # Kan şekeri kayıtları
            cur.execute("""
                SELECT h.kullanici_adi, h.isim, o.tarih_saat, 'Kan Şekeri', o.seviye_mgdl
                FROM hasta h
                JOIN tbl_olcum o ON h.kullanici_adi = o.hasta_tc
                WHERE h.doktor_tc = %s
                ORDER BY o.tarih_saat DESC
            """, (tc_doc,))
            for tc, isim, ts, tip, val in cur.fetchall():
                self.tree.insert("", "end", values=(
                    tc,
                    isim,
                    ts.strftime("%d.%m.%Y %H:%M:%S"),
                    tip,
                    val
                ))
            # Belirti kayıtları
            cur.execute("""
                SELECT h.kullanici_adi, h.isim, s.tarih_saat, 'Belirti', st.tur
                FROM hasta h
                JOIN tbl_semptom s ON h.kullanici_adi = s.hasta_tc
                JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                WHERE h.doktor_tc = %s
                ORDER BY s.tarih_saat DESC
            """, (tc_doc,))
            for tc, isim, ts, tip, val in cur.fetchall():
                self.tree.insert("", "end", values=(
                    tc,
                    isim,
                    ts.strftime("%d.%m.%Y %H:%M:%S"),
                    tip,
                    val
                ))

        else:
            # 2) Min/Max kan seviyesi filtresi
            if min_v and max_v:
                try:
                    mn, mx = int(min_v), int(max_v)
                    cur.execute("""
                        SELECT h.kullanici_adi, h.isim, o.tarih_saat, 'Kan Şekeri', o.seviye_mgdl
                        FROM hasta h
                        JOIN tbl_olcum o ON h.kullanici_adi = o.hasta_tc
                        WHERE h.doktor_tc = %s
                          AND o.seviye_mgdl BETWEEN %s AND %s
                        ORDER BY o.tarih_saat DESC
                    """, (tc_doc, mn, mx))
                    for tc, isim, ts, tip, val in cur.fetchall():
                        self.tree.insert("", "end", values=(
                            tc,
                            isim,
                            ts.strftime("%d.%m.%Y %H:%M:%S"),
                            tip,
                            val
                        ))
                except ValueError:
                    messagebox.showerror("Hata", "Min/Max seviye sayısal olmalı.")

            # 3) Belirti filtresi
            if symptom:
                cur.execute("""
                    SELECT h.kullanici_adi, h.isim, s.tarih_saat, 'Belirti', st.tur
                    FROM hasta h
                    JOIN tbl_semptom s ON h.kullanici_adi = s.hasta_tc
                    JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                    WHERE h.doktor_tc = %s
                      AND st.tur = %s
                    ORDER BY s.tarih_saat DESC
                """, (tc_doc, symptom))
                for tc, isim, ts, tip, val in cur.fetchall():
                    self.tree.insert("", "end", values=(
                        tc,
                        isim,
                        ts.strftime("%d.%m.%Y %H:%M:%S"),
                        tip,
                        val
                    ))

        cur.close()
        conn.close()
   
class DoctorGraphFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Başlık
        tk.Label(self, text="Doktor — Grafikler", font=("Arial", 16, "bold"))\
          .pack(pady=10)

        # Butonlar
        btnf = tk.Frame(self)
        btnf.pack(pady=5)
        tk.Button(btnf, text="Kan Şekeri & Diyet/Egzersiz", command=self.plot_glucose_diet_ex)\
          .pack(side="left", padx=5)
        tk.Button(btnf, text="Egzersiz/Diyet Uyum Oranları", command=self.plot_ex_diet)\
          .pack(side="left", padx=5)
        tk.Button(self, text="Geri", command=controller.go_back)\
          .pack(side="bottom", pady=5)

        # Canvas placeholder
        self.canvas = None

    def _clear_canvas(self):
        """Önceki grafiği temizle."""
        if self.canvas:
            self.canvas.get_tk_widget().pack_forget()
            plt.close('all')
            self.canvas = None

    def _draw(self, fig):
        """Yeni matplotlib figürünü ekrana çiz."""
        self._clear_canvas()
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def plot_ex_diet(self):
        """Egzersiz ve diyet uyum oranlarını pasta grafiğiyle göster. (Değişmedi)"""
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Egzersiz uyum
        cur.execute(
            "SELECT COUNT(*) FROM tbl_egzersiz_takip WHERE hasta_tc=%s", (tc,))
        total_ex = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT COUNT(*) FROM tbl_egzersiz_takip "
            "WHERE hasta_tc=%s AND yapilan_egzersiz NOT LIKE 'Egzersiz yapılmadı'", (tc,))
        done_ex = cur.fetchone()[0] or 0

        # Diyet uyum
        cur.execute(
            "SELECT COUNT(*) FROM tbl_diyet_takip WHERE hasta_tc=%s", (tc,))
        total_di = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT COUNT(*) FROM tbl_diyet_takip "
            "WHERE hasta_tc=%s AND uygulanan_diyet NOT LIKE 'Diyet uygulanmadı'", (tc,))
        done_di = cur.fetchone()[0] or 0

        cur.close(); conn.close()

        ex_data = [done_ex, max(total_ex - done_ex, 0)]
        di_data = [done_di, max(total_di - done_di, 0)]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))
        if total_ex:
            ax1.pie(ex_data, labels=["Yapıldı","Yapılmadı"], autopct="%1.1f%%", startangle=90)
        else:
            ax1.text(0.5,0.5,"Kayıt yok",ha="center",va="center")
        ax1.set_title("Egzersiz Uyum")

        if total_di:
            ax2.pie(di_data, labels=["Yapıldı","Yapılmadı"], autopct="%1.1f%%", startangle=90)
        else:
            ax2.text(0.5,0.5,"Kayıt yok",ha="center",va="center")
        ax2.set_title("Diyet Uyum")

        plt.tight_layout()
        self._draw(fig)

    def plot_glucose_diet_ex(self):
        """
        Kan şekerini zaman serisi olarak çizer ve
        diyet/egzersiz olaylarını o olay anındaki kan şekeri değeri
        üzerine farklı markerlarla işaretler.
        """
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 1) Tüm glukoz ölçümleri
        cur.execute(
            "SELECT tarih_saat, seviye_mgdl FROM tbl_olcum "
            "WHERE hasta_tc=%s ORDER BY tarih_saat", (tc,))
        glucose = cur.fetchall()

        # 2) Diyet ve egzersiz zamanları
        cur.execute(
            "SELECT tarih_saat FROM tbl_diyet_plani "
            "WHERE hasta_tc=%s ORDER BY tarih_saat", (tc,))
        diet_times = [row[0] for row in cur.fetchall()]

        cur.execute(
            "SELECT tarih_saat FROM tbl_egzersiz_oneri "
            "WHERE hasta_tc=%s ORDER BY tarih_saat", (tc,))
        ex_times = [row[0] for row in cur.fetchall()]

        cur.close(); conn.close()

        # Zaman ve değer listeleri
        times = [t for t, _ in glucose]
        values = [v for _, v in glucose]

        # Olay anındaki en yakın ölçüm değerlerini bul
        def nearest_value(event_time):
            # glucose listesinde en yakın zamanı seç
            nearest = min(glucose, key=lambda gv: abs((gv[0] - event_time).total_seconds()))
            return nearest

        diet_pts = [nearest_value(t) for t in diet_times]
        ex_pts   = [nearest_value(t) for t in ex_times]

        # Grafik oluştur
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(times, values, marker='o', linestyle='-', label='Kan Şekeri')

        # Diyet olaylarını kare marker ile işaretle
        diet_x = [dt for dt, _ in diet_pts]
        diet_y = [val for _, val in diet_pts]
        ax.scatter(diet_x, diet_y, marker='s', label='Diyet')

        # Egzersiz olaylarını üçgen marker ile işaretle
        ex_x = [dt for dt, _ in ex_pts]
        ex_y = [val for _, val in ex_pts]
        ax.scatter(ex_x, ex_y, marker='^', label='Egzersiz')

        # Legend ve etiketler
        ax.set_title("Kan Şekeri ve Diyet/Egzersiz Etkileşimi")
        ax.set_xlabel("Tarih/Saat")
        ax.set_ylabel("mg/dL")
        fig.autofmt_xdate()
        ax.legend(loc='upper left')

        self._draw(fig)

class PatientGraphFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Başlık
        tk.Label(self, text="Günlük Kan Şekeri Değerleri", font=("Arial", 16, "bold")).pack(pady=10)

        # Seçim ve kontrol butonları
        btnf = tk.Frame(self)
        btnf.pack(pady=5)

        # Tarih seçimi
        tk.Label(btnf, text="Tarih (GG.AA.YYYY):").pack(side="left", padx=5)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%d.%m.%Y"))
        self.date_entry = tk.Entry(btnf, textvariable=self.date_var, width=10)
        self.date_entry.pack(side="left", padx=5)
        tk.Button(btnf, text="Tarihe Göre Grafik Göster", command=self.plot_for_selected).pack(side="left", padx=5)

        # Tablo görünümü
        tk.Button(btnf, text="Kayıtlı Ölçümler ve Günlük Ortalamalar", command=self.show_tables).pack(side="left", padx=5)
        # Yenile ve geri
        tk.Button(btnf, text="Yenile", command=self.refresh_current).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri", command=controller.go_back).pack(side="left", padx=5)

        # Grafik ve tablo tutucular
        self.canvas = None
        self.table = None
        self.mode = 'daily'

    def tkraise(self, above=None):
        super().tkraise(above)
        # Ekran gelince seçili moda göre göster
        if self.mode == 'table':
            self.show_tables()
        else:
            self.plot_daily()

    def _clear_visuals(self):
        if self.canvas:
            self.canvas.get_tk_widget().pack_forget()
            plt.close('all')
            self.canvas = None
        if self.table:
            self.table.destroy()
            self.table = None

    def _draw(self, fig):
        self._clear_visuals()
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def plot_daily(self):
        self.mode = 'daily'
        self._clear_visuals()
        tc = self.controller.current_user_tc
        today = datetime.now().strftime("%Y-%m-%d")
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT DATE_FORMAT(tarih_saat, '%H:%i'), seviye_mgdl "
            "FROM tbl_olcum "
            "WHERE hasta_tc=%s AND DATE(tarih_saat)=%s "
            "ORDER BY tarih_saat",
            (tc, today)
        )
        data = cur.fetchall()
        cur.close(); conn.close()

        times = [row[0] for row in data]
        values = [row[1] for row in data]

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(times, values, marker='o', linestyle='-')
        ax.set_title(f"{datetime.now().strftime('%d.%m.%Y')} Tarihli Kan Şekeri Değerleri")
        ax.set_xlabel("Saat")
        ax.set_ylabel("mg/dL")
        ax.grid(True)
        fig.autofmt_xdate()

        self._draw(fig)

    def plot_for_selected(self):
        date_str = self.date_var.get().strip()
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            messagebox.showerror("Geçersiz Tarih", "Tarih GG.AA.YYYY formatında olmalı.")
            return
        self.mode = 'daily'
        self._clear_visuals()
        tc = self.controller.current_user_tc
        date_mysql = dt.strftime("%Y-%m-%d")
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT DATE_FORMAT(tarih_saat, '%H:%i'), seviye_mgdl "
            "FROM tbl_olcum "
            "WHERE hasta_tc=%s AND DATE(tarih_saat)=%s "
            "ORDER BY tarih_saat",
            (tc, date_mysql)
        )
        data = cur.fetchall()
        cur.close(); conn.close()

        times = [row[0] for row in data]
        values = [row[1] for row in data]

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(times, values, marker='o', linestyle='-')
        ax.set_title(f"{date_str} Tarihli Kan Şekeri Değerleri")
        ax.set_xlabel("Saat")
        ax.set_ylabel("mg/dL")
        ax.grid(True)
        fig.autofmt_xdate()

        self._draw(fig)

    def show_tables(self):
        self.mode = 'table'
        self._clear_visuals()
        tc = self.controller.current_user_tc
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        # Tüm kayıtlı ölçümler
        cur.execute(
            "SELECT DATE_FORMAT(tarih_saat, '%d.%m.%Y %H:%i'), seviye_mgdl "
            "FROM tbl_olcum "
            "WHERE hasta_tc=%s "
            "ORDER BY tarih_saat",
            (tc,)
        )
        measurements = cur.fetchall()
        # Günlük ortalamalar
        cur.execute(
            "SELECT DATE(tarih_saat), ROUND(AVG(seviye_mgdl),1) "
            "FROM tbl_olcum "
            "WHERE hasta_tc=%s "
            "GROUP BY DATE(tarih_saat) "
            "ORDER BY DATE(tarih_saat)",
            (tc,)
        )
        averages = cur.fetchall()
        cur.close(); conn.close()

        # Tablo oluştur
        self.table = ttk.Treeview(self, columns=("col1","col2"), show="headings", height=20)
        self.table.heading("col1", text="Zaman")
        self.table.heading("col2", text="Değer / Ortalama")
        self.table.column("col1", anchor="center", width=200)
        self.table.column("col2", anchor="center", width=200)

        # Satır ekleme
        self.table.insert("", "end", values=("=== Tüm Kayıtlı Ölçümler ===",""))
        for i, (zaman, deger) in enumerate(measurements):
            tag = 'even' if i % 2 == 0 else 'odd'
            self.table.insert("", "end", values=(zaman, deger), tags=(tag,))
        self.table.insert("", "end", values=("=== Günlük Ortalamalar ===",""))
        for j, (tarih, ort) in enumerate(averages):
            tag = 'even' if j % 2 == 0 else 'odd'
            self.table.insert("", "end", values=(tarih.strftime("%d.%m.%Y"), ort), tags=(tag,))

        # Satır renkleri
        self.table.tag_configure('even', background='#f0f0ff')
        self.table.tag_configure('odd', background='#ffffff')

        self.table.pack(padx=20, pady=10, fill="both", expand=True)

    def refresh_current(self):
        if self.mode == 'table':
            self.show_tables()
        else:
            self.plot_daily()

class InsulinViewFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="İnsülin Takip", font=("Arial", 16, "bold")).pack(pady=10)

        frm = tk.Frame(self)
        frm.pack(pady=5)

        # Tek gün filtreleme
        tk.Label(frm, text="Tarih (DD.MM.YYYY):", bg="white") \
          .grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.date_entry = tk.Entry(frm, width=12)
        self.date_entry.grid(row=0, column=1, sticky="w", pady=2)
        tk.Button(frm, text="O Günün Kayıtları", command=self.show_for_date) \
          .grid(row=0, column=2, padx=10)

        # Aralıkla filtreleme
        tk.Label(frm, text="Başlangıç (DD.MM.YYYY):", bg="white") \
          .grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.start_entry = tk.Entry(frm, width=12)
        self.start_entry.grid(row=1, column=1, sticky="w", pady=2)

        tk.Label(frm, text="Bitiş (DD.MM.YYYY):", bg="white") \
          .grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self.end_entry = tk.Entry(frm, width=12)
        self.end_entry.grid(row=2, column=1, sticky="w", pady=2)

        tk.Button(frm, text="Aralığa Göre Göster", command=self.show_range) \
          .grid(row=1, column=2, rowspan=2, padx=10)

        # Geri butonu
        tk.Button(self, text="Geri", command=controller.go_back).pack(pady=5)

        # Sonuçları gösterecek Text widget
        self.txt = tk.Text(self, width=80, height=15)
        self.txt.pack(pady=10)

    def show_for_date(self):
        """Tek bir gün için DD.MM.YYYY formatında filtrele."""
        date_str = self.date_entry.get().strip()
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y")
            mysql_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Geçersiz Tarih", "Lütfen DD.MM.YYYY formatında girin.")
            return

        tc = self.controller.current_user_tc
        query = """
            SELECT tarih_saat, birim_u
            FROM tbl_insulin
            WHERE hasta_tc=%s AND DATE(tarih_saat)=%s
            ORDER BY tarih_saat DESC
        """
        params = (tc, mysql_date)
        self._run_and_display(query, params)

    def show_range(self):
        """Başlangıç ve bitiş tarihlerine göre DD.MM.YYYY formatında filtrele."""
        start_str = self.start_entry.get().strip()
        end_str   = self.end_entry.get().strip()
        try:
            dt_start = datetime.strptime(start_str, "%d.%m.%Y")
            dt_end   = datetime.strptime(end_str,   "%d.%m.%Y")
            start_date = dt_start.strftime("%Y-%m-%d")
            end_date   = dt_end.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Geçersiz Tarih", "Başlangıç ve Bitiş için DD.MM.YYYY formatını kullanın.")
            return

        tc = self.controller.current_user_tc
        query = """
            SELECT tarih_saat, birim_u
            FROM tbl_insulin
            WHERE hasta_tc=%s
              AND DATE(tarih_saat) BETWEEN %s AND %s
            ORDER BY tarih_saat DESC
        """
        params = (tc, start_date, end_date)
        self._run_and_display(query, params)

    def _run_and_display(self, query, params):
        """Sorguyu çalıştır ve Text widget'a sonuçları yaz."""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
        except Exception as e:
            messagebox.showerror("Veri Hatası", str(e))
            return
        finally:
            cur.close()
            conn.close()

        self.txt.delete("1.0", "end")
        if not rows:
            self.txt.insert("end", "Kayıt bulunamadı.")
            return

        for ts, birim in rows:
            self.txt.insert(
                "end",
                f"{ts.strftime('%d.%m.%Y %H:%M:%S')} | {birim} ünite\n"
            )

class UyariFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="white")

        # Stil ayarları
        s = ttk.Style(self)
        # Kalın başlık fontu
        s.configure("Treeview.Heading", font=("Arial", 12, "bold"))
        # Satır yüksekliği ve font
        s.configure("Treeview", rowheight=24, font=("Arial", 10))
        
        # Başlık
        tk.Label(self, text="Doktor — Uyarılar",
                 font=("Arial", 20, "bold"), bg="white")\
            .pack(pady=10)

        # Hasta seçimi
        patients = controller.get_my_patients()  # [(tc, isim), ...]
        options = [tc for tc, _ in patients]
        self.patient_var = controller.frames["DoctorFrame"].patient_var
        if options:
            self.patient_var.set(options[0])
        ttk.OptionMenu(self, self.patient_var, self.patient_var.get(), *options)\
            .pack(pady=5)

        # Acil Uyarılar Tablosu
        self.acil_tv = ttk.Treeview(
            self,
            columns=("tarih_saat", "durum", "uyari_tipi", "mesaj"),
            show="headings",
            selectmode="none"
        )
        for col in ("tarih_saat", "durum", "uyari_tipi", "mesaj"):
            self.acil_tv.heading(col, text=col.replace("_", " ").title(), anchor="center")
            self.acil_tv.column(col, anchor="w", width=150 if col!="mesaj" else 400)
        self.acil_tv.tag_configure("evenrow", background="#e6f2ff")
        self.acil_tv.tag_configure("oddrow",  background="white")
        tk.Label(self, text="ACİL UYARILAR",
                 font=("Arial", 15, "bold"), bg="white")\
            .pack(pady=(15,0), anchor="w", padx=10)
        self.acil_tv.pack(padx=10, pady=(0,10), fill="x")

        # Diğer Uyarılar Tablosu
        self.diger_tv = ttk.Treeview(
            self,
            columns=("tarih_saat", "durum", "uyari_tipi", "mesaj"),
            show="headings",
            selectmode="none"
        )
        for col in ("tarih_saat", "durum", "uyari_tipi", "mesaj"):
            self.diger_tv.heading(col, text=col.replace("_", " ").title(), anchor="w")
            self.diger_tv.column(col, anchor="w", width=150 if col!="mesaj" else 400)
        self.diger_tv.tag_configure("evenrow", background="#e6f2ff")
        self.diger_tv.tag_configure("oddrow",  background="white")
        tk.Label(self, text="DİĞER UYARILAR",
                 font=("Arial", 15, "bold"), bg="white")\
            .pack(pady=(15,0), anchor="w", padx=10)
        self.diger_tv.pack(padx=10, pady=(0,10), fill="x")

        # Yenile / Geri butonları
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=10, fill="x")
        tk.Button(btnf, text="Yenile", width=12, command=self.load_warnings)\
            .pack(side="left", padx=5)
        tk.Button(btnf, text="Geri", width=12, command=controller.go_back)\
            .pack(side="right", padx=5)
    def tkraise(self, aboveThis=None):
        super().tkraise(aboveThis)
        self.load_warnings()


    def load_warnings(self):
        tc = self.patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute(
            "SELECT tarih_saat, durum, uyarı_tipi, mesaj "
            "FROM uyarilar "
            "WHERE hasta_tc=%s "
            "ORDER BY tarih_saat DESC",
            (tc,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        # Tablo temizle
        for tv in (self.acil_tv, self.diger_tv):
            for iid in tv.get_children():
                tv.delete(iid)

        # Satır ekle (alternating renklerle)
        acil_rows  = [r for r in rows if r[2] == "Acil Uyarı"]
        diger_rows = [r for r in rows if r[2] != "Acil Uyarı"]

        for tv, data in ((self.acil_tv, acil_rows), (self.diger_tv, diger_rows)):
            for idx, (tarih, durum, tip, msg) in enumerate(data):
                tag = "evenrow" if idx%2==0 else "oddrow"
                tv.insert("", "end", values=(tarih, durum, tip, msg), tags=(tag,))

# -----------------------------------------------------
# Uygulamayı Çalıştır
# -----------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
