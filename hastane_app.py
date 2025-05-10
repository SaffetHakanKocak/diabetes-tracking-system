import tkinter as tk
from tkinter import messagebox
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

# — EKLENECEK: Ölçüm aralıkları sabitleri
VALID_WINDOWS = {
    'Sabah':  (time(7,0),  time(8,0)),
    'Öğle':   (time(12,0), time(13,0)),
    'İkindi': (time(15,0), time(16,0)),
    'Akşam':  (time(18,0), time(19,0)),
    'Gece':   (time(22,0), time(23,0)),
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
    for cond, rule_syms, diet, ex in RECOMMENDATION_RULES:
        if cond(seviye) and any(s in semptoms for s in rule_syms):
            return diet, ex
    # hiçbir kural tetiklenmediyse
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
    UyariFrame, NewPatientFrame,   # son eleman UyariFrame olmalı
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
        canvas.create_image(0,0, image=controller.bg_image, anchor="nw")
        sw, sh = controller.winfo_screenwidth(), controller.winfo_screenheight()
        canvas.create_image(sw//2, sh//3,
                            image=controller.logo_image, anchor="center")
        canvas.create_text(
            sw//2,
            sh//3 + controller.logo_image.height()//2 + 20,
            text="Diyabet Takip Sistemine Hoşgeldiniz",
            font=("Arial",24,"bold"),
            fill="navy"
        )
        ileri = tk.Button(self, text="İleri →",
                          font=("Arial",12,"bold"),
                          bg="navy", fg="white",
                          command=lambda: controller.show_frame("LoginFrame"))
        ileri.place(relx=0.98, rely=0.98, anchor="se")
        ileri.lift()

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

        # Başlık
        self.header = tk.Label(self, font=("Arial", 18, "bold"), bg="white")
        self.header.pack(pady=15)

        # Hasta seçimi
        self.patient_var = tk.StringVar()
        tk.Label(self, text="Hasta:", font=("Arial", 12), bg="white").pack(pady=5)
        self.patient_menu = tk.OptionMenu(self, self.patient_var, "")
        self.patient_menu.pack()

        # İşlem butonları
        btn_container = tk.Frame(self, bg="white")
        btn_container.pack(pady=20)

        buttons = [
            ("Yeni Hasta",      "NewPatientFrame"),
            ("Ölçüm Girişi",    "DoctorOlcumFrame"),
            ("Belirti Girişi",  "SymptomFrame"),
            ("Egzersiz Öneri",  "EgzersizOnerFrame"),
            ("Diyet Planı",     "DiyetPlanFrame"),
            ("Veri Görüntüle",  "DataViewFrame"),
            ("Filtrele",        "DoctorFilterFrame"),
            ("Grafikler",       "DoctorGraphFrame"),
            ("Uyarılar",        "UyariFrame"),       # — EKLENECEK
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
        # Hasta listesini doldur
        menu = self.patient_menu["menu"]
        menu.delete(0, "end")
        for tc, isim in self.controller.get_my_patients():
            menu.add_command(
                label=f"{tc} – {isim}",
                command=lambda v=tc: self.patient_var.set(v)
            )
        # İlk hastayı seçili yap
        patients = self.controller.get_my_patients()
        if patients:
            self.patient_var.set(patients[0][0])
        super().tkraise(above)


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
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)
        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        labels = ["TC","Şifre","Resim URL","E-posta",
                  "Doğum (YYYY-MM-DD)","Cinsiyet","İsim","Şehir"]
        self.entries = {}
        for i, lbl in enumerate(labels):
            tk.Label(frm, text=lbl+":", bg="white").grid(
                row=i, column=0, sticky="e", pady=2, padx=5
            )
            e = tk.Entry(frm, width=30)
            e.grid(row=i, column=1, pady=2, padx=5)
            self.entries[lbl] = e

        bf = tk.Frame(self, bg="white")
        bf.pack(pady=15)
        tk.Button(bf, text="Kaydet", width=12,
                  command=self.save).pack(side="left", padx=5)
        tk.Button(bf, text="Geri", width=12,
                  command=controller.go_back).pack(side="right", padx=5)

    def save(self):
        vals = [e.get().strip() for e in self.entries.values()]
        if any(not v for v in vals):
            messagebox.showwarning("Eksik Bilgi","Lütfen tüm alanları doldurun.")
            return
        tc, pw, img, em, dob, gn, ad, se = vals

        # TC doğrulama: 11 hane ve sadece rakam
        if not (tc.isdigit() and len(tc) == 11):
            messagebox.showerror("Geçersiz TC",
                                 "TC kimlik numarası 11 haneli olmalı ve sadece rakam içermelidir.")
            return

        # Şifre hash'leme
        salt = bcrypt.gensalt(rounds=HASH_ROUNDS)
        pw_hash = bcrypt.hashpw(pw.encode(), salt)

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO hasta "
                "(kullanici_adi,sifre,resim,email,dogum_tarihi,cinsiyet,isim,sehir,doktor_tc) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (tc, pw_hash, img, em, dob, gn, ad, se, self.controller.current_user_tc)
            )
            conn.commit()
            cur.close(); conn.close()
            # Hasta kayıt bilgilerini e-posta ile gönder
            send_email(em, tc, pw, self.controller.current_user_name)
            messagebox.showinfo("Başarılı","Hasta kaydedildi.")
            self.controller.show_frame("DoctorFrame")
        except mysql.connector.Error as e:
            messagebox.showerror("Hata", e)


# -----------------------------------------------------
# Doktor için Ölçüm Girişi
# -----------------------------------------------------
class DoctorOlcumFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Doktor — Yeni Ölçüm Girişi",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)

        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)
        # Hasta TC seçimi (DoctorFrame’den aktarılan var)
        tk.Label(frm, text="Hasta TC:", bg="white").grid(row=0,column=0,sticky="e")
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0,column=1, sticky="w", pady=2)

        # Diğer alanlar
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white").grid(row=1,column=0,sticky="e")
        self.tarih = tk.Entry(frm, width=25); self.tarih.grid(row=1,column=1, pady=2)
        tk.Label(frm, text="Seviye (mg/dL):", bg="white").grid(row=2,column=0,sticky="e")
        self.seviye = tk.Entry(frm, width=25); self.seviye.grid(row=2,column=1, pady=2)
        tk.Label(frm, text="Tür:", bg="white").grid(row=3,column=0,sticky="e")
        self.tur_var = tk.StringVar(value="Sabah")
        self.tur_menu = tk.OptionMenu(frm, self.tur_var, *['Sabah','Öğle','İkindi','Akşam','Gece'])
        self.tur_menu.grid(row=3,column=1, pady=2)

        bf = tk.Frame(self, bg="white")
        bf.pack(pady=15)
        tk.Button(bf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(bf, text="Geri",   command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        # DoctorFrame’den seçili hastayı al
        sec = self.controller.frames["DoctorFrame"].patient_var.get()
        self.tc.config(text=sec)
        super().tkraise(above)

    def save(self):
        tc       = self.tc.cget("text")           # Seçili hastanın TC’si
        tr_input = self.tarih.get().strip()       # DD.MM.YYYY HH:MM:SS
        sv       = int(self.seviye.get())         # Seviye (mg/dL)
        tur      = self.tur_var.get()             # Ölçüm türü

        try:
            # — Tarih/Saat parse & format —
            dt_local = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                              .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt_local.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()

            # 1) Ölçümü kaydet
            cur.execute(
                "INSERT INTO tbl_olcum (hasta_tc, tarih_saat, seviye_mgdl, tur) "
                "VALUES (%s, %s, %s, %s)",
                (tc, tr, sv, tur)
            )

            # 2) Kritik seviye uyarıları
            if sv < 70:
                tip = "Acil Uyarı"
                msg = "Hastanın kan şekeri seviyesi 70 mg/dL'nin altına düştü."
            elif sv > 200:
                tip = "Acil Müdahale Uyarısı"
                msg = "Hastanın kan şekeri 200 mg/dL'nin üzerinde."
            elif 111 <= sv <= 150:
                tip = "Takip Uyarısı"
                msg = "Kan şekeri 111–150 mg/dL arasında. İzlenmeli."
            elif 151 <= sv <= 200:
                tip = "İzleme Uyarısı"
                msg = "Kan şekeri 151–200 mg/dL arasında. Kontrol gerekli."
            else:
                tip = None

            if tip:
                cur.execute(
                    "INSERT INTO uyarilar (hasta_tc, tarih_saat, mesaj) VALUES (%s, %s, %s)",
                    (tc, tr, msg)
                )
                messagebox.showwarning(tip, msg)

            # 3) Ölçüm zamanı kontrolü
            start, end = VALID_WINDOWS[tur]
            saat = dt_local.timetz().replace(tzinfo=None)
            if not (start <= saat <= end):
                msg2 = "Ölçüm zamanı aralık dışında; ortalamaya dahil edilmeyecek."
                cur.execute(
                    "INSERT INTO uyarilar (hasta_tc, tarih_saat, mesaj) VALUES (%s, %s, %s)",
                    (tc, tr, msg2)
                )
                messagebox.showwarning("Zaman Uyarısı", msg2)

            # 4) İnsülin dozu hesapla ve kaydet
            avg, dose = get_insulin_dose_for_day(conn, tc, tr)
            if dose > 0:
                cur.execute(
                    "INSERT INTO tbl_insulin (hasta_tc, tarih_saat, birim_u) VALUES (%s, %s, %s)",
                    (tc, tr, dose)
                )
                messagebox.showinfo("İnsülin Önerisi",
                                    f"Günlük ort. kan şekeri: {avg:.1f} mg/dL → {dose} ünite")

            # 5) Semptomlara göre diyet/egzersiz önerisi
            cur.execute(
                "SELECT st.tur FROM tbl_semptom s "
                "JOIN semptom_turleri st ON s.semptom_tur_id=st.id "
                "WHERE s.hasta_tc=%s ORDER BY s.tarih_saat DESC LIMIT 5",
                (tc,)
            )
            sems = [r[0] for r in cur.fetchall()]
            diet, exercise = get_recommendation(sv, sems)

            # 6) Diyet planı kaydet (diet None değilse)
            if diet:
               cur.execute("SELECT id FROM diyet_turleri WHERE tur=%s", (diet,))
               row = cur.fetchone()
               if row:
                  diyet_id = row[0]
                  cur.execute(
                    "INSERT INTO tbl_diyet_plani "
                    "(hasta_tc, tarih_saat, diyet_tur_id) "
                    "VALUES (%s, %s, %s)",
                    (tc, tr, diyet_id)
                )


            # 7) Egzersiz önerisi kaydet (exercise None değilse)
            if exercise:
                cur.execute(
                "SELECT id FROM egzersiz_turleri WHERE tur=%s", (exercise,)
                )
                row2 = cur.fetchone()
                if row2:
                     egz_id = row2[0]
                     cur.execute(
                        "INSERT INTO tbl_egzersiz_oneri "
                        "(hasta_tc, tarih_saat, egzersiz_tur_id) "
                        "VALUES (%s, %s, %s)",
                        (tc, tr, egz_id)
                     )


            # 🔥 Burada commit ve bağlantı kapatmayı **try** bloğu içinde bırakıyoruz
            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo(
                "Başarılı",
                f"Ölçüm ve otomatik öneriler kaydedildi:\nDiyet: {diet or 'Yok'}\nEgzersiz: {exercise or 'Yok'}"
            )
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
        except Exception as e:
            messagebox.showerror("Hata", e)
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

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Doktor — Egzersiz Önerisi",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)

        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        # Hasta TC
        tk.Label(frm, text="Hasta TC:", bg="white")\
            .grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0, column=1, sticky="w", pady=4)

        # Tarih/Saat (DD.MM.YYYY HH:MM:SS)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white")\
            .grid(row=1, column=0, sticky="e", padx=5, pady=4)
        self.tarih = tk.Entry(frm, font=("Arial",12), width=25)
        self.tarih.grid(row=1, column=1, pady=4)
        # Placeholder olarak güncel zamanı ekleyelim
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        # Egzersiz türü
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, tur FROM egzersiz_turleri")
        self.egz_turleri = cur.fetchall()
        cur.close(); conn.close()

        egz_list = [tur for _, tur in self.egz_turleri]
        tk.Label(frm, text="Egzersiz Türü:", bg="white")\
            .grid(row=2, column=0, sticky="e", padx=5, pady=4)
        self.egz_var = tk.StringVar(value=egz_list[0])
        tk.OptionMenu(frm, self.egz_var, *egz_list).grid(row=2, column=1, pady=4, sticky="w")

        # Butonlar
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=15)
        tk.Button(btnf, text="Kaydet", width=12, command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri",   width=12, command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        # Hasta TC’sini güncelle
        self.tc.config(text=self.controller.frames["DoctorFrame"].patient_var.get())
        super().tkraise(above)

    def save(self):
        tc      = self.tc.cget("text")
        tr_input = self.tarih.get().strip()
        egz_tur = self.egz_var.get()

        try:
            # Tarih parse: DD.MM.YYYY HH:MM:SS
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                     .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()

            # Seçili egzersiz türünün ID'si
            egz_id = next(i for i, tur in self.egz_turleri if tur == egz_tur)

            # Sadece tarih ve tür ekliyoruz; süre/kalori alanı yok
            cur.execute(
                "INSERT INTO tbl_egzersiz_oneri "
                "(hasta_tc, tarih_saat, egzersiz_tur_id) "
                "VALUES (%s, %s, %s)",
                (tc, tr, egz_id)
            )

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı", "Egzersiz önerisi kaydedildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
        except Exception as e:
            messagebox.showerror("Hata", e)

# -----------------------------------------------------
# Doktor için Diyet Planı
# -----------------------------------------------------
class DiyetPlanFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Arka plan
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Başlık
        tk.Label(self, text="Doktor — Diyet Planı",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)

        frm = tk.Frame(self, bg="white")
        frm.pack(pady=5)

        # Hasta TC
        tk.Label(frm, text="Hasta TC:", bg="white")\
            .grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.tc = tk.Label(frm, text="", bg="white")
        self.tc.grid(row=0, column=1, sticky="w", pady=4)

        # Tarih/Saat (DD.MM.YYYY HH:MM:SS)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white")\
            .grid(row=1, column=0, sticky="e", padx=5, pady=4)
        self.tarih = tk.Entry(frm, font=("Arial",12), width=25)
        self.tarih.grid(row=1, column=1, pady=4)
        # Placeholder olarak güncel zamanı ekleyelim
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        # Diyet Türü
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, tur FROM diyet_turleri")
        self.diyet_turleri = cur.fetchall()
        cur.close(); conn.close()

        diyet_list = [tur for _, tur in self.diyet_turleri]
        tk.Label(frm, text="Diyet Türü:", bg="white")\
            .grid(row=2, column=0, sticky="e", padx=5, pady=4)
        self.diyet_var = tk.StringVar(value=diyet_list[0])
        tk.OptionMenu(frm, self.diyet_var, *diyet_list)\
            .grid(row=2, column=1, pady=4, sticky="w")

        # Butonlar
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=15)
        tk.Button(btnf, text="Kaydet", width=12, command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri",   width=12, command=controller.go_back).pack(side="right", padx=5)

    def tkraise(self, above=None):
        # Hasta TC’sini güncelle
        self.tc.config(text=self.controller.frames["DoctorFrame"].patient_var.get())
        super().tkraise(above)

    def save(self):
        tc       = self.tc.cget("text")
        tr_input = self.tarih.get().strip()
        diyet    = self.diyet_var.get()

        try:
            # Tarih parse: DD.MM.YYYY HH:MM:SS
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                     .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()

            # Seçili diyet türünün ID'si
            diyet_id = next(i for i, tur in self.diyet_turleri if tur == diyet)

            # Sadece hasta_tc, tarih_saat, diyet_tur_id ekliyoruz
            cur.execute(
                "INSERT INTO tbl_diyet_plani "
                "(hasta_tc, tarih_saat, diyet_tur_id) "
                "VALUES (%s, %s, %s)",
                (tc, tr, diyet_id)
            )

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı", "Diyet planı kaydedildi.")
            self.controller.show_frame("DoctorFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
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

        # Başlık
        self.header = tk.Label(self, font=("Arial", 18, "bold"), bg="white")
        self.header.pack(pady=15)

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
            ("Belirti Takip",      "PatientSymptomView"),
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
        super().tkraise(above)

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
                     font=("Arial", 12)).grid(row=i, column=0, sticky="e", padx=10, pady=8)

        # Girdi alanları
        self.tarih = tk.Entry(form, font=("Arial", 12), width=25)
        self.tarih.grid(row=0, column=1, padx=10, pady=8)

        self.seviye = tk.Entry(form, font=("Arial", 12), width=25)
        self.seviye.grid(row=1, column=1, padx=10, pady=8)

        self.tur_var = tk.StringVar(value="Sabah")
        tk.OptionMenu(form, self.tur_var, *['Sabah', 'Öğle', 'İkindi', 'Akşam', 'Gece']) \
            .grid(row=2, column=1, padx=10, pady=8, sticky="w")

        # Butonlar
        btn_frame = tk.Frame(self, bg="white")
        btn_frame.pack(pady=(20, 10))

        tk.Button(btn_frame, text="Kaydet", width=12,
                  command=self.save).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Geri", width=12,
                  command=controller.go_back).pack(side="left", padx=5)

    def save(self):
        tc       = self.controller.current_user_tc
        tr_input = self.tarih.get().strip()       # DD.MM.YYYY HH:MM:SS
        sv       = int(self.seviye.get())
        tur      = self.tur_var.get()

        try:
            # — Tarih parse & format —
            dt_local = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                              .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr = dt_local.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()

            # 1) Ölçümü kaydet
            cur.execute(
                "INSERT INTO tbl_olcum (hasta_tc, tarih_saat, seviye_mgdl, tur) "
                "VALUES (%s, %s, %s, %s)",
                (tc, tr, sv, tur)
            )

            # 2) Kritik seviye uyarıları (aynı kod bloğu)
            if sv < 70:
                tip = "Acil Uyarı"
                msg = "Hastanın kan şekeri seviyesi 70 mg/dL'nin altına düştü."
            elif sv > 200:
                tip = "Acil Müdahale Uyarısı"
                msg = "Hastanın kan şekeri 200 mg/dL'nin üzerinde."
            elif 111 <= sv <= 150:
                tip = "Takip Uyarısı"
                msg = "Kan şekeri 111–150 mg/dL arasında. İzlenmeli."
            elif 151 <= sv <= 200:
                tip = "İzleme Uyarısı"
                msg = "Kan şekeri 151–200 mg/dL arasında. Kontrol gerekli."
            else:
                tip = None

            if tip:
                cur.execute(
                    "INSERT INTO uyarilar (hasta_tc, tarih_saat, mesaj) VALUES (%s, %s, %s)",
                    (tc, tr, msg)
                )
                messagebox.showwarning(tip, msg)

            # 3) Saat aralığı kontrolü
            start, end = VALID_WINDOWS[tur]
            saat = dt_local.timetz().replace(tzinfo=None)
            if not (start <= saat <= end):
                msg2 = "Ölçüm zamanı aralık dışında; ortalamaya dahil edilmeyecek."
                cur.execute(
                    "INSERT INTO uyarilar (hasta_tc, tarih_saat, mesaj) VALUES (%s, %s, %s)",
                    (tc, tr, msg2)
                )
                messagebox.showwarning("Zaman Uyarısı", msg2)

            # 4) İnsülin dozu ve plan/egzersiz önerileri…
            avg, dose = get_insulin_dose_for_day(conn, tc, tr)
            if dose > 0:
                cur.execute(
                    "INSERT INTO tbl_insulin (hasta_tc, tarih_saat, birim_u) VALUES (%s, %s, %s)",
                    (tc, tr, dose)
                )
                messagebox.showinfo("İnsülin Önerisi",
                                    f"Günlük ort. kan şekeri: {avg:.1f} mg/dL → {dose} ml")

            # (Opsiyonel: semptom+öneri blokları burada da eklenebilir)

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı", "Ölçüm kaydedildi.")
            self.controller.show_frame("PatientFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
        except Exception as e:
            messagebox.showerror("Hata", e)

            # İnsülin dozu hesapla ve kaydet
            avg, dose = get_insulin_dose_for_day(conn, tc, tr)
            if dose > 0:
                cur.execute(
                    "INSERT INTO tbl_insulin (hasta_tc, tarih_saat, birim_u) VALUES (%s,%s,%s)",
                    (tc, tr, dose)
                )
                messagebox.showinfo(
                    "İnsülin Önerisi",
                    f"Günlük ort. kan şekeri: {avg:.1f} mg/dL → {dose} ml"
                )

            conn.commit()
            cur.close()
            conn.close()

            messagebox.showinfo("Başarılı","Ölçüm kaydedildi.")
            self.controller.show_frame("PatientFrame")

        except ValueError:
            messagebox.showerror(
                "Geçersiz Tarih/Saat",
                "Lütfen DD.MM.YYYY HH:MM:SS formatında girin."
            )
        except Exception as e:
            messagebox.showerror("Hata", e)

# -----------------------------------------------------
# Hasta — Egzersiz Uyum Takibi
# -----------------------------------------------------
class EgzersizTakipFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Egzersiz Uyum Takibi",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)
        frm = tk.Frame(self, bg="white"); frm.pack(pady=5)

        tk.Label(frm, text="Tarih/Saat (YYYY-MM-DD HH:MM:SS):", bg="white").grid(row=0,column=0,sticky="e")
        self.tarih = tk.Entry(frm, width=25); self.tarih.grid(row=0,column=1,pady=2)
        self.yap_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frm, text="Yapıldı", variable=self.yap_var, bg="white").grid(row=1,column=1, sticky="w")

        bf = tk.Frame(self, bg="white"); bf.pack(pady=15)
        tk.Button(bf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(bf, text="Geri",   command=controller.go_back).pack(side="right", padx=5)

    def save(self):
        tc, tr, yap = (
            self.controller.current_user_tc,
            self.tarih.get(),
            self.yap_var.get()
        )
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO tbl_egzersiz_takip (hasta_tc,tarih_saat,yapildi) VALUES (%s,%s,%s)",
                (tc,tr,yap)
            )
            conn.commit(); cur.close(); conn.close()
            messagebox.showinfo("Başarılı","Egzersiz uyum bilgisi kaydedildi.")
            self.controller.show_frame("PatientFrame")
        except Exception as e:
            messagebox.showerror("Hata", e)

# -----------------------------------------------------
# Hasta — Diyet Uyum Takibi
# -----------------------------------------------------
class DiyetTakipFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Diyet Uyum Takibi",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)
        frm = tk.Frame(self, bg="white"); frm.pack(pady=5)

        tk.Label(frm, text="Tarih/Saat (YYYY-MM-DD HH:MM:SS):", bg="white").grid(row=0,column=0,sticky="e")
        self.tarih = tk.Entry(frm, width=25); self.tarih.grid(row=0,column=1,pady=2)
        self.uyg_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frm, text="Uygulandı", variable=self.uyg_var, bg="white").grid(row=1,column=1, sticky="w")

        bf = tk.Frame(self, bg="white"); bf.pack(pady=15)
        tk.Button(bf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(bf, text="Geri",   command=controller.go_back).pack(side="right", padx=5)

    def save(self):
        tc, tr, uyg = (
            self.controller.current_user_tc,
            self.tarih.get(),
            self.uyg_var.get()
        )
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO tbl_diyet_takip (hasta_tc,tarih_saat,uygulandi) VALUES (%s,%s,%s)",
                (tc,tr,uyg)
            )
            conn.commit(); cur.close(); conn.close()
            messagebox.showinfo("Başarılı","Diyet uyum bilgisi kaydedildi.")
            self.controller.show_frame("PatientFrame")
        except Exception as e:
            messagebox.showerror("Hata", e)

# -----------------------------------------------------
# Hasta — Belirti Görüntüle (basit liste)
# -----------------------------------------------------
class PatientSymptomEntryFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        tk.Label(self, text="Belirti Bildirimi",
                 font=("Arial",16,"bold"), bg="white").pack(pady=10)
        frm = tk.Frame(self, bg="white"); frm.pack(pady=5)

        tk.Label(frm, text="Tarih/Saat (YYYY-MM-DD HH:MM:SS):", bg="white")\
            .grid(row=0, column=0, sticky="e")
        self.tarih = tk.Entry(frm, width=25); self.tarih.grid(row=0, column=1, pady=2)

        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, tur FROM semptom_turleri")
        self.semptom_turleri = cur.fetchall()
        cur.close(); conn.close()

        semptom_isimler = [t for _, t in self.semptom_turleri]
        self.semptom_var = tk.StringVar(value=semptom_isimler[0])
        tk.Label(frm, text="Semptom Türü:", bg="white").grid(row=1, column=0, sticky="e")
        tk.OptionMenu(frm, self.semptom_var, *semptom_isimler).grid(row=1, column=1, pady=2)

        tk.Label(frm, text="Açıklama:", bg="white").grid(row=2, column=0, sticky="ne")
        self.aciklama = tk.Text(frm, width=30, height=4); self.aciklama.grid(row=2, column=1, pady=2)

        btnf = tk.Frame(self, bg="white"); btnf.pack(pady=15)
        tk.Button(btnf, text="Kaydet", command=self.save).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri",   command=controller.go_back).pack(side="right", padx=5)

    def save(self):
        tc = self.controller.current_user_tc
        tr = self.tarih.get().strip()
        secili = self.semptom_var.get()
        acik = self.aciklama.get("1.0","end").strip()
        sem_id = next(i for i,t in self.semptom_turleri if t == secili)

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO tbl_semptom "
                "(hasta_tc, tarih_saat, semptom_tur_id, aciklama) "
                "VALUES (%s,%s,%s,%s)",
                (tc, tr, sem_id, acik)
            )
            conn.commit(); cur.close(); conn.close()
            messagebox.showinfo("Başarılı","Belirti bildirimi kaydedildi.")
            self.controller.show_frame("PatientFrame")
        except Exception as e:
            messagebox.showerror("Hata", e)

class DoctorFilterFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        tk.Label(self, text="Doktor — Hastaları Filtrele", font=("Arial",16,"bold")).pack(pady=10)
        frm = tk.Frame(self); frm.pack(pady=5)
        # Örnek: min/max kan seviyesi
        tk.Label(frm, text="Min mg/dL:").grid(row=0,column=0)
        self.min_var = tk.Entry(frm); self.min_var.grid(row=0,column=1)
        tk.Label(frm, text="Max mg/dL:").grid(row=1,column=0)
        self.max_var = tk.Entry(frm); self.max_var.grid(row=1,column=1)
        tk.Button(frm, text="Filtrele", command=self.filter).grid(row=2,column=0,columnspan=2,pady=10)
        tk.Button(self, text="Geri", command=controller.go_back).pack(side="bottom", pady=5)
        self.txt = tk.Text(self, width=80, height=15); self.txt.pack()

    def filter(self):
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        q = "SELECT tarih_saat,seviye_mgdl,tur FROM tbl_olcum WHERE hasta_tc=%s AND seviye_mgdl BETWEEN %s AND %s"
        params = (tc, int(self.min_var.get()), int(self.max_var.get()))
        conn = mysql.connector.connect(**DB_CONFIG); cur=conn.cursor()
        cur.execute(q, params)
        rows = cur.fetchall(); cur.close(); conn.close()
        self.txt.delete("1.0","end")
        for r in rows:
            self.txt.insert("end", f"{r[0]} | {r[1]} mg/dL | {r[2]}\n")
   
class DoctorGraphFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        tk.Label(self, text="Doktor — Grafikler", font=("Arial",16,"bold")).pack(pady=10)
        btnf = tk.Frame(self); btnf.pack()
        tk.Button(btnf, text="Kan Şekeri Zaman Serisi", command=self.plot_glucose).pack(side="left", padx=5)
        tk.Button(btnf, text="Egzersiz/Diyet Etkisi", command=self.plot_ex_diet).pack(side="left", padx=5)
        tk.Button(self, text="Geri", command=controller.go_back).pack(side="bottom", pady=5)
        self.canvas = None

    def _draw(self, fig):
        if self.canvas: self.canvas.get_tk_widget().destroy()
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw(); self.canvas.get_tk_widget().pack()

    def plot_glucose(self):
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG); cur=conn.cursor()
        cur.execute("SELECT tarih_saat,seviye_mgdl FROM tbl_olcum WHERE hasta_tc=%s ORDER BY tarih_saat", (tc,))
        data = cur.fetchall(); cur.close(); conn.close()
        dates = [d[0] for d in data]; vals = [d[1] for d in data]
        fig, ax = plt.subplots()
        ax.plot(dates, vals)
        ax.set_title("Zaman Bazlı Kan Şekeri")
        ax.set_xlabel("Tarih/Saat"), ax.set_ylabel("mg/dL")
        self._draw(fig)

    def plot_ex_diet(self):
        # Burada egzersiz ve diyet tablolarını join edip grafiğe dökebilirsiniz.
        # Örneğin: tarih bakımından birleştirip yan yana iki çizgi plot’u vs.
        pass

class PatientGraphFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        tk.Label(self, text="Günlük Kan Şekeri + Ortalama", font=("Arial",16,"bold")).pack(pady=10)
        tk.Button(self, text="Grafiğe Dön", command=self.plot).pack(pady=5)
        tk.Button(self, text="Geri",      command=controller.go_back).pack(pady=5)
        self.canvas = None

    def plot(self):
        tc = self.controller.current_user_tc
        conn = mysql.connector.connect(**DB_CONFIG); cur=conn.cursor()
        # günlük ortalama
        cur.execute("""
            SELECT DATE(tarih_saat), AVG(seviye_mgdl)
            FROM tbl_olcum
            WHERE hasta_tc=%s
            GROUP BY DATE(tarih_saat)
            ORDER BY DATE(tarih_saat)
        """, (tc,))
        data = cur.fetchall(); cur.close(); conn.close()
        dates = [d[0] for d in data]; avgs = [d[1] for d in data]
        fig, ax = plt.subplots()
        ax.bar(dates, avgs)
        ax.set_title("Günlük Ortalama Kan Şekeri")
        ax.set_xlabel("Tarih"), ax.set_ylabel("mg/dL")
        if self.canvas: self.canvas.get_tk_widget().destroy()
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw(); self.canvas.get_tk_widget().pack()


class InsulinViewFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent); self.controller = controller
        tk.Label(self, text="İnsülin Takip", font=("Arial",16,"bold")).pack(pady=10)
        frm = tk.Frame(self); frm.pack(pady=5)
        tk.Label(frm, text="Başlangıç (YYYY-MM-DD):").grid(row=0,column=0)
        self.start = tk.Entry(frm); self.start.grid(row=0,column=1)
        tk.Label(frm, text="Bitiş (YYYY-MM-DD):").grid(row=1,column=0)
        self.end   = tk.Entry(frm); self.end.grid(row=1,column=1)
        tk.Button(frm, text="Göster", command=self.show).grid(row=2,column=0,columnspan=2,pady=10)
        tk.Button(self, text="Geri",   command=controller.go_back).pack(pady=5)
        self.txt = tk.Text(self, width=80, height=15); self.txt.pack()

    def show(self):
        tc = self.controller.current_user_tc
        q  = """SELECT tarih_saat,birim_u 
                FROM tbl_insulin 
                WHERE hasta_tc=%s AND DATE(tarih_saat) BETWEEN %s AND %s
                ORDER BY tarih_saat DESC"""
        params = (tc, self.start.get(), self.end.get())
        conn = mysql.connector.connect(**DB_CONFIG); cur=conn.cursor()
        cur.execute(q, params)
        rows = cur.fetchall(); cur.close(); conn.close()
        self.txt.delete("1.0","end")
        for t,b in rows:
            self.txt.insert("end", f"{t} | {b} ünite\n")

class UyariFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Başlık
        tk.Label(
            self,
            text="Doktor — Uyarılar",
            font=("Arial", 16, "bold"),
            bg="white"
        ).pack(pady=10)

        # Hasta seçimi
        # controller.get_my_patients() -> [(tc, isim), ...]
        patients = controller.get_my_patients()
        options = [tc for tc, _ in patients]

        # patient_var, DoctorFrame tarafından tanımlı
        var = controller.frames["DoctorFrame"].patient_var
        # Varsayılan değeri ilk hastanın TC'si olarak ayarla
        if options:
            var.set(options[0])
        else:
            var.set("")

        # OptionMenu(master, variable, default, *values)
        self.option_menu = tk.OptionMenu(self, var, var.get(), *options)
        self.option_menu.config(width=20)
        self.option_menu.pack(pady=5)

        # Uyarıları listeleyecek metin alanı
        self.text = tk.Text(self, width=80, height=20)
        self.text.pack(pady=10)

        # Yenile ve Geri butonları
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=5, fill="x")
        tk.Button(btnf, text="Yenile", width=12,
                  command=self.load_warnings).pack(side="left", padx=5)
        tk.Button(btnf, text="Geri", width=12,
                  command=controller.go_back).pack(side="right", padx=5)

    def load_warnings(self):
        """
        Seçili hastanın tüm uyarılarını çeker ve Text widget içine yazar.
        Okundu bilgisini işaretlemek isterseniz burada UPDATE sorgusu ekleyebilirsiniz.
        """
        tc = self.controller.frames["DoctorFrame"].patient_var.get()

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute(
            "SELECT tarih_saat, mesaj, okundu "
            "FROM uyarilar "
            "WHERE hasta_tc=%s "
            "ORDER BY tarih_saat DESC",
            (tc,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        self.text.delete("1.0", "end")
        for tarih, mesaj, okundu in rows:
            flag = "✓" if okundu else "•"
            self.text.insert("end", f"{flag} {tarih} — {mesaj}\n\n")

# -----------------------------------------------------
# Uygulamayı Çalıştır
# -----------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
