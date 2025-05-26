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
import os
from matplotlib.dates import DateFormatter

VALID_WINDOWS = {
    'Sabah':  (datetime.strptime("07:00", "%H:%M").time(),  datetime.strptime("08:00", "%H:%M").time()),
    'Öğle':   (datetime.strptime("12:00", "%H:%M").time(),  datetime.strptime("13:00", "%H:%M").time()),
    'İkindi': (datetime.strptime("15:00", "%H:%M").time(),  datetime.strptime("16:00", "%H:%M").time()),
    'Akşam':  (datetime.strptime("18:00", "%H:%M").time(),  datetime.strptime("19:00", "%H:%M").time()),
    'Gece':   (datetime.strptime("22:00", "%H:%M").time(),  datetime.strptime("23:00", "%H:%M").time()),
}
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
        if cond(seviye) and s_set == r_set:
            return diet, ex
    return None, None
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
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hasta Takip Sistemi")
        self.state("zoomed")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=12,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.bg_image = ImageTk.PhotoImage(
            Image.open("background.png").resize((sw, sh), Image.LANCZOS)
        )
        logo = Image.open("logo.png")
        logo_w = sw // 4
        logo_h = int(logo.height/logo.width * logo_w)
        self.logo_image = ImageTk.PhotoImage(logo.resize((logo_w, logo_h), Image.LANCZOS))
        self.current_user_tc   = None   
        self.current_user_name = None   
        self.current_role      = None   
        self.history           = []
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
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
    UyariFrame,   
):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("WelcomeFrame")

    def show_frame(self, page_name):
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
class WelcomeFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        canvas = tk.Canvas(self, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_image(0, 0, image=controller.bg_image, anchor="nw")
        sw, sh = controller.winfo_screenwidth(), controller.winfo_screenheight()
        logo_y = sh // 3
        canvas.create_image(sw // 2, logo_y, image=controller.logo_image, anchor="center")
        text_y = logo_y + controller.logo_image.height() // 2 + 60  
        canvas.create_text(
            sw // 2,
            text_y,
            text="Diyabet Takip Sistemine Hoş Geldiniz",
            font=("Arial", 32, "bold"), 
            fill="navy"
        )
        devam_buton_y = text_y + 80
        devam_btn = tk.Button(self,
                              text="Devam et",
                              font=("Arial", 16, "bold"),
                              bg="navy",
                              fg="white",
                              padx=20, pady=10,
                              command=lambda: controller.show_frame("LoginFrame"))
        devam_btn.place(x=sw // 2, y=devam_buton_y, anchor="n")
class LoginFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        card = tk.Frame(self, bg="#eaf6fb", bd=2, relief="flat")
        card.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(
            card, text="Giriş Yap", 
            bg="#eaf6fb", fg="#242424",
            font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, columnspan=2, pady=(24, 16), padx=36)
        tk.Label(card, text="TC Kimlik No:", bg="#eaf6fb", font=("Segoe UI", 13, "bold"), anchor="e", width=14)\
            .grid(row=1, column=0, sticky="e", pady=10, padx=(18,4))
        self.tc_entry = tk.Entry(card, font=("Segoe UI", 13), width=25)
        self.tc_entry.grid(row=1, column=1, pady=10, padx=(4,18))
        tk.Label(card, text="Şifre:", bg="#eaf6fb", font=("Segoe UI", 13, "bold"), anchor="e", width=14)\
            .grid(row=2, column=0, sticky="e", pady=10, padx=(18,4))
        self.pw_entry = tk.Entry(card, font=("Segoe UI", 13), width=25, show="*")
        self.pw_entry.grid(row=2, column=1, pady=10, padx=(4,18))
        btnf = tk.Frame(card, bg="#eaf6fb")
        btnf.grid(row=3, column=0, columnspan=2, pady=(18, 16))
        ttk.Button(
            btnf, text="Giriş Yap", width=15, style="Modern.TButton", command=self.login
        ).pack(side="left", padx=8)
        ttk.Button(
            btnf, text="Çıkış", width=15, style="Modern.TButton", command=controller.destroy
        ).pack(side="left", padx=8)
        for child in card.winfo_children():
            child.grid_configure(pady=6)

    def login(self):
        tc = self.tc_entry.get().strip()
        pw = self.pw_entry.get().strip()
        if not (tc.isdigit() and len(tc) == 11):
            messagebox.showerror("Geçersiz TC", "TC kimlik numarası 11 haneli olmalı.")
            return
        if not pw:
            messagebox.showwarning("Eksik Bilgi", "Lütfen şifrenizi girin.")
            return

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "SELECT sifre, isim FROM doktor WHERE kullanici_adi=%s",
                (tc,)
            )
            row = cur.fetchone()
            if row:
                stored_hash = row[0]
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')
                if bcrypt.checkpw(pw.encode('utf-8'), stored_hash):
                    self.controller.current_role      = "doctor"
                    self.controller.current_user_tc   = tc
                    self.controller.current_user_name = row[1]
                    cur.close(); conn.close()
                    self.controller.show_frame("DoctorFrame")
                    return
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
class DoctorFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        top_card = tk.Frame(self, bg="#f4f6fb")
        top_card.pack(pady=28)

        self.photo_label = tk.Label(top_card, bg="#f4f6fb", bd=0)
        self.photo_label.pack(side="left", padx=24)

        text_frame = tk.Frame(top_card, bg="#f4f6fb")
        text_frame.pack(side="left")

        self.header = tk.Label(
            text_frame,
            font=("Arial", 21, "bold"),
            bg="#f4f6fb",
            fg="#252a34"
        )
        self.header.pack(anchor="w", pady=(0, 8))

        patient_card = tk.Frame(text_frame, bg="white", bd=0, relief="groove", padx=18, pady=12)
        patient_card.pack(anchor="w")
        tk.Label(
            patient_card,
            text="Hasta:",
            font=("Segoe UI", 12, "bold"),
            bg="white",
            fg="#3a435e"
        ).pack(side="left", padx=(0, 12))

        self.patient_var = tk.StringVar()
        self.patient_menu = ttk.Combobox(
            patient_card,
            textvariable=self.patient_var,
            font=("Segoe UI", 11),
            state="readonly",
            width=25
        )
        self.patient_menu.pack(side="left")
        btn_card = tk.Frame(self, bg="#f4f6fb")
        btn_card.pack(pady=38)

        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=12,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )

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
        for idx, (label, frame_name) in enumerate(buttons):
            row, col = divmod(idx, 3)
            btn = ttk.Button(
                btn_card,
                text=label,
                style="Modern.TButton",
                width=18,
                command=lambda f=frame_name: controller.show_frame(f)
            )
            btn.grid(row=row, column=col, padx=18, pady=14, sticky="ew")

        nav = tk.Frame(self, bg="#f4f6fb")
        nav.pack(side="bottom", fill="x", pady=16)
        ttk.Button(
            nav, text="Geri",
            style="Modern.TButton",
            command=controller.go_back
        ).pack(side="left", padx=35)
        ttk.Button(
            nav, text="Çıkış",
            style="Modern.TButton",
            command=controller.destroy
        ).pack(side="right", padx=35)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

    def tkraise(self, above=None):
        self.header.config(text=f"Hoşgeldiniz Dr. {self.controller.current_user_name}")

        doctor_tc = self.controller.current_user_tc
        photo_path = self.get_doctor_photo_path(doctor_tc)
        if photo_path:
            try:
                img = Image.open(photo_path).resize((86, 86))
                photo = ImageTk.PhotoImage(img)
                self.photo_label.config(image=photo)
                self.photo_label.image = photo
            except Exception as e:
                print(f"Fotoğraf yüklenemedi: {e}")
        patients = self.controller.get_my_patients()
        tcs = [tc for tc, isim in patients]   
        self.patient_menu['values'] = tcs
        if tcs:
            current = self.patient_var.get()
            if not current or current not in tcs:
                self.patient_var.set(tcs[0])

        super().tkraise(above)


    def get_doctor_photo_path(self, tc):
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
class NewPatientFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        form_bg = "#eaf6fb"
        card = tk.Frame(self, bg=form_bg, bd=0, relief="flat", padx=28, pady=18)
        card.place(relx=0.5, rely=0.5, anchor="c")
        header_frame = tk.Frame(card, bg="#ffe0b2")
        header_frame.pack(fill="x", pady=(0, 16))
        tk.Label(
            header_frame,
            text="Yeni Hasta Kayıt",
            font=("Arial", 26, "bold"),
            bg="#ffe0b2",
            fg="#232946",
            pady=12
        ).pack(padx=20, fill="x")
        frm = tk.Frame(card, bg=form_bg)
        frm.pack(pady=(10, 0), padx=10)

        labels = ["TC", "Resim", "E-posta", "Doğum (DD.MM.YYYY)", "Cinsiyet(E-K)", "İsim", "Şehir"]
        self.entries = {}

        for i, lbl in enumerate(labels):
            row_frame = tk.Frame(frm, bg=form_bg)
            row_frame.grid(row=2*i, column=0, sticky="ew", pady=0)
            row_frame.grid_columnconfigure(1, weight=1)
            tk.Label(row_frame, text=lbl + ":", bg=form_bg,
                    font=("Segoe UI", 12, "bold"), anchor="e", width=22)\
                .grid(row=0, column=0, sticky="e", pady=8, padx=(0, 8))

            if lbl == "Resim":
                entry = tk.Entry(row_frame, width=29, font=("Segoe UI", 12))
                entry.grid(row=0, column=1, sticky="w", pady=8, padx=(0, 4))
                self.entries[lbl] = entry

                sec_button = ttk.Button(
                    row_frame,
                    text="Seç",
                    width=6,
                    style="Small.TButton",
                    command=lambda e=entry: self.select_file(e)
                )
                sec_button.grid(row=0, column=2, padx=(4, 0), sticky="w")
            else:
                entry = tk.Entry(row_frame, width=34, font=("Segoe UI", 12))
                entry.grid(row=0, column=1, sticky="w", pady=8)
                self.entries[lbl] = entry

            if i < len(labels)-1:
                sep = ttk.Separator(frm, orient="horizontal")
                sep.grid(row=2*i+1, column=0, sticky="ew", padx=0, pady=0)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=8,
            background="#fff",
            foreground="#232946",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#232946')]
        )
        style.configure(
            "Small.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=3,
            background="#fff",
            foreground="#232946",
            borderwidth=0
        )
        bf = tk.Frame(card, bg=form_bg)
        bf.pack(pady=(25, 2))
        ttk.Button(bf, text="Kaydet", width=15,
                   style="Modern.TButton", command=self.save).pack(side="left", padx=10)
        ttk.Button(bf, text="Geri", width=15,
                   style="Modern.TButton", command=controller.go_back).pack(side="right", padx=10)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

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

        if not (tc.isdigit() and len(tc) == 11):
            messagebox.showerror("Geçersiz TC",
                                 "TC kimlik numarası 11 haneli olmalı ve sadece rakam içermelidir.")
            return

        random_password = "{:06d}".format(random.randint(0, 999999))
        salt = bcrypt.gensalt(rounds=HASH_ROUNDS)
        pw_hash = bcrypt.hashpw(random_password.encode(), salt)

        try:
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
class DoctorOlcumFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        card = tk.Frame(self, bg="#eaf6fb", bd=0, relief="flat", padx=55, pady=32)
        card.place(relx=0.5, rely=0.23, anchor="n")
        header_frame = tk.Frame(card, bg="#ffe0b2")
        header_frame.pack(fill="x", pady=(0, 20))
        tk.Label(
            header_frame,
            text="Doktor — Yeni Ölçüm Girişi",
            font=("Arial", 25, "bold"),
            bg="#ffe0b2",
            fg="#232946",
            pady=12
        ).pack(padx=25, fill="x")
        frm = tk.Frame(card, bg="#eaf6fb")
        frm.pack(pady=(7, 0), padx=10)
        tk.Label(frm, text="Hasta TC:", bg="#eaf6fb", font=("Segoe UI", 13, "bold"),
                 width=32, anchor="e").grid(row=0, column=0, sticky="e", pady=12, padx=(0,8))
        self.tc = tk.Label(frm, text="", bg="#eaf6fb", font=("Segoe UI", 13), anchor="w")
        self.tc.grid(row=0, column=1, sticky="w", pady=12)

        ttk.Separator(frm, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", padx=6)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="#eaf6fb",
                 font=("Segoe UI", 13, "bold"), width=32, anchor="e")\
            .grid(row=2, column=0, sticky="e", pady=12, padx=(0,8))
        self.tarih = tk.Entry(frm, width=28, font=("Segoe UI", 13))
        self.tarih.grid(row=2, column=1, sticky="w", pady=12)

        ttk.Separator(frm, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", padx=6)
        tk.Label(frm, text="Seviye (mg/dL):", bg="#eaf6fb", font=("Segoe UI", 13, "bold"),
                 width=32, anchor="e").grid(row=4, column=0, sticky="e", pady=12, padx=(0,8))
        self.seviye = tk.Entry(frm, width=28, font=("Segoe UI", 13))
        self.seviye.grid(row=4, column=1, sticky="w", pady=12)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 13, "bold"),
            padding=11,
            background="#fff",
            foreground="#232946",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#232946')]
        )
        bf = tk.Frame(card, bg="#eaf6fb")
        bf.pack(pady=(24, 4))
        ttk.Button(bf, text="Kaydet", width=16,
                   style="Modern.TButton", command=self.save).pack(side="left", padx=15)
        ttk.Button(bf, text="Geri", width=16,
                   style="Modern.TButton", command=controller.go_back).pack(side="right", padx=15)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

    def tkraise(self, above=None):
        sec = self.controller.frames["DoctorFrame"].patient_var.get()
        self.tc.config(text=sec)
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.tarih.delete(0, tk.END)
        self.tarih.insert(0, now)
        super().tkraise(above)

    def save(self):
        tc = self.tc.cget("text").strip()
        tarih_input = self.tarih.get().strip()
        seviye_input = self.seviye.get().strip()

        try:
            dt = datetime.strptime(tarih_input, "%d.%m.%Y %H:%M:%S")
            tarih_mysql = dt.strftime("%Y-%m-%d %H:%M:%S")
            seviye = int(seviye_input)

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
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
class SymptomFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        card = tk.Frame(self, bg="#eaf6fb", bd=0, relief="flat", padx=45, pady=24)
        card.place(relx=0.5, rely=0.2, anchor="n")
        header_frame = tk.Frame(card, bg="#ffe0b2")
        header_frame.pack(fill="x", pady=(0, 20))
        tk.Label(
            header_frame,
            text="Doktor — Belirti Girişi",
            font=("Arial", 24, "bold"),
            bg="#ffe0b2",
            fg="#232946",
            pady=10
        ).pack(padx=16, fill="x")
        frm = tk.Frame(card, bg="#eaf6fb")
        frm.pack(pady=(4, 0), padx=10)
        tk.Label(frm, text="Hasta TC:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="e").grid(row=0, column=0, sticky="e", pady=9, padx=(0, 8))
        self.tc = tk.Label(frm, text="", bg="#eaf6fb", font=("Segoe UI", 12), anchor="w")
        self.tc.grid(row=0, column=1, sticky="w", pady=9)

        ttk.Separator(frm, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", padx=6)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="#eaf6fb",
                 font=("Segoe UI", 12, "bold"), width=34, anchor="e")\
            .grid(row=2, column=0, sticky="e", pady=9, padx=(0,8))
        self.tarih = tk.Entry(frm, width=28, font=("Segoe UI", 12))
        self.tarih.grid(row=2, column=1, sticky="w", pady=9)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        ttk.Separator(frm, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", padx=6)
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, tur FROM semptom_turleri")
        self.semptom_turleri = cur.fetchall()
        cur.close(); conn.close()
        semptom_isimler = [t for _, t in self.semptom_turleri]

        tk.Label(frm, text="Semptom Türü:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="e").grid(row=4, column=0, sticky="e", pady=9, padx=(0, 8))
        self.semptom_var = tk.StringVar(value=semptom_isimler[0])
        ttk.Combobox(frm, textvariable=self.semptom_var, values=semptom_isimler,
                     font=("Segoe UI", 12), state="readonly", width=26)\
            .grid(row=4, column=1, sticky="w", pady=9)

        ttk.Separator(frm, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", padx=6)
        tk.Label(frm, text="Açıklama:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="ne").grid(row=6, column=0, sticky="ne", pady=9, padx=(0, 8))
        self.aciklama = tk.Text(frm, width=30, height=4, font=("Segoe UI", 12))
        self.aciklama.grid(row=6, column=1, pady=9, sticky="w")
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=9,
            background="#fff",
            foreground="#232946",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#232946')]
        )

        btnf = tk.Frame(card, bg="#eaf6fb")
        btnf.pack(pady=20)
        ttk.Button(btnf, text="Kaydet", width=15,
                   style="Modern.TButton", command=self.save).pack(side="left", padx=10)
        ttk.Button(btnf, text="Geri", width=15,
                   style="Modern.TButton", command=controller.go_back).pack(side="right", padx=10)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

    def tkraise(self, above=None):
        self.tc.config(text=self.controller.frames["DoctorFrame"].patient_var.get())
        super().tkraise(above)

    def save(self):
        tc = self.tc.cget("text")
        tr_input = self.tarih.get().strip()
        secili = self.semptom_var.get()
        acik = self.aciklama.get("1.0","end").strip()
        sem_id = next(i for i,t in self.semptom_turleri if t == secili)

        try:
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S")
            tr = dt.strftime("%Y-%m-%d %H:%M:%S")  

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
class EgzersizOnerFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        card = tk.Frame(self, bg="#eaf6fb", bd=0, relief="flat", padx=48, pady=28)
        card.place(relx=0.5, rely=0.2, anchor="n")
        header_frame = tk.Frame(card, bg="#ffe0b2")
        header_frame.pack(fill="x", pady=(0, 22))
        tk.Label(
            header_frame,
            text="Doktor — Egzersiz Önerisi",
            font=("Arial", 24, "bold"),
            bg="#ffe0b2",
            fg="#232946",
            pady=10
        ).pack(padx=20, fill="x")
        frm = tk.Frame(card, bg="#eaf6fb")
        frm.pack(pady=(6, 0), padx=12)
        tk.Label(frm, text="Hasta TC:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="e").grid(row=0, column=0, sticky="e", pady=9, padx=(0, 8))
        self.tc = tk.Label(frm, text="", bg="#eaf6fb", font=("Segoe UI", 12), anchor="w")
        self.tc.grid(row=0, column=1, sticky="w", pady=9)

        ttk.Separator(frm, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", padx=6)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="#eaf6fb",
                 font=("Segoe UI", 12, "bold"), width=34, anchor="e")\
            .grid(row=2, column=0, sticky="e", pady=9, padx=(0,8))
        self.tarih = tk.Entry(frm, width=28, font=("Segoe UI", 12))
        self.tarih.grid(row=2, column=1, sticky="w", pady=9)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        ttk.Separator(frm, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", padx=6)
        self.info_label = tk.Label(
            frm,
            text="",
            font=("Segoe UI", 11, "italic"),
            bg="#eaf6fb",
            fg="#595959",
            anchor="center",       
            justify="center"      
        )
        self.info_label.grid(row=4, column=0, columnspan=2, pady=(7, 0), sticky="ew")
        tk.Label(frm, text="Egzersiz Türü:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="e").grid(row=5, column=0, sticky="e", pady=9, padx=(0, 8))
        self.egz_var = tk.StringVar()
        self.egz_menu = ttk.Combobox(frm, textvariable=self.egz_var, font=("Segoe UI", 12), state="readonly", width=26)
        self.egz_menu.grid(row=5, column=1, sticky="w", pady=9)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=9,
            background="#fff",
            foreground="#232946",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#232946')]
        )

        btnf = tk.Frame(card, bg="#eaf6fb")
        btnf.pack(pady=20)
        ttk.Button(btnf, text="Kaydet", width=15,
                   style="Modern.TButton", command=self.save).pack(side="left", padx=10)
        ttk.Button(btnf, text="Geri", width=15,
                   style="Modern.TButton", command=controller.go_back).pack(side="right", padx=10)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

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
            cur.execute(
                "SELECT seviye_mgdl FROM doktor_kan_olcum "
                "WHERE hasta_tc=%s ORDER BY tarih_saat DESC LIMIT 1",
                (tc,)
            )
            row = cur.fetchone()
            seviye = row[0] if row else None
            cur.execute("""
                SELECT st.tur
                FROM tbl_semptom s
                JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                WHERE s.hasta_tc = %s
            """, (tc,))
            semptom_rows = cur.fetchall()
            semptoms = [t for (t,) in semptom_rows]
            cur.execute("SELECT id, tur FROM egzersiz_turleri")
            self.egz_turleri = cur.fetchall()
            all_exercises = [tur for _, tur in self.egz_turleri]
            exercise = None
            if seviye is not None:
                _, exercise = get_recommendation(seviye, semptoms)

            if exercise:
                self.info_label.config(
                    text=f"Sistem tarafından {exercise} öneriliyor.",
                    font=("Segoe UI", 11, "bold"),
                    fg="#8B5E3C",
                    anchor="center",
                    justify="center"
                )
            else:
                self.info_label.config(text="", font=("Segoe UI", 11, "italic"), fg="#595959", anchor="center", justify="center")

            self.egz_menu['values'] = all_exercises
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
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S")
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
class DiyetPlanFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        card = tk.Frame(self, bg="#eaf6fb", bd=0, relief="flat", padx=48, pady=28)
        card.place(relx=0.5, rely=0.2, anchor="n")
        header_frame = tk.Frame(card, bg="#ffe0b2")
        header_frame.pack(fill="x", pady=(0, 22))
        tk.Label(
            header_frame,
            text="Doktor — Diyet Planı",
            font=("Arial", 24, "bold"),
            bg="#ffe0b2",
            fg="#232946",
            pady=10
        ).pack(padx=20, fill="x")
        frm = tk.Frame(card, bg="#eaf6fb")
        frm.pack(pady=(6, 0), padx=12)
        tk.Label(frm, text="Hasta TC:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="e").grid(row=0, column=0, sticky="e", pady=9, padx=(0, 8))
        self.tc = tk.Label(frm, text="", bg="#eaf6fb", font=("Segoe UI", 12), anchor="w")
        self.tc.grid(row=0, column=1, sticky="w", pady=9)

        ttk.Separator(frm, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", padx=6)
        tk.Label(frm, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="#eaf6fb",
                 font=("Segoe UI", 12, "bold"), width=34, anchor="e")\
            .grid(row=2, column=0, sticky="e", pady=9, padx=(0,8))
        self.tarih = tk.Entry(frm, width=28, font=("Segoe UI", 12))
        self.tarih.grid(row=2, column=1, sticky="w", pady=9)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        ttk.Separator(frm, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", padx=6)
        self.info_label = tk.Label(
            frm,
            text="",
            font=("Segoe UI", 11, "italic"),
            bg="#eaf6fb",
            fg="#595959",
            anchor="center",       
            justify="center"       
        )
        self.info_label.grid(row=4, column=0, columnspan=2, pady=(7, 0), sticky="ew")
        tk.Label(frm, text="Diyet Türü:", bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 width=24, anchor="e").grid(row=5, column=0, sticky="e", pady=9, padx=(0, 8))
        self.diyet_var = tk.StringVar()
        self.diyet_menu = ttk.Combobox(frm, textvariable=self.diyet_var, font=("Segoe UI", 12), state="readonly", width=26)
        self.diyet_menu.grid(row=5, column=1, sticky="w", pady=9)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=9,
            background="#fff",
            foreground="#232946",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#232946')]
        )

        btnf = tk.Frame(card, bg="#eaf6fb")
        btnf.pack(pady=20)
        ttk.Button(btnf, text="Kaydet", width=15,
                   style="Modern.TButton", command=self.save).pack(side="left", padx=10)
        ttk.Button(btnf, text="Geri", width=15,
                   style="Modern.TButton", command=controller.go_back).pack(side="right", padx=10)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

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
            cur.execute(
                "SELECT seviye_mgdl FROM doktor_kan_olcum "
                "WHERE hasta_tc=%s ORDER BY tarih_saat DESC LIMIT 1",
                (tc,)
            )
            row = cur.fetchone()
            seviye = row[0] if row else None
            cur.execute("""
                SELECT st.tur
                FROM tbl_semptom s
                JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                WHERE s.hasta_tc = %s
            """, (tc,))
            semptom_rows = cur.fetchall()
            semptoms = [t for (t,) in semptom_rows]
            cur.execute("SELECT id, tur FROM diyet_turleri")
            self.diyet_turleri = cur.fetchall()
            all_diets = [tur for _, tur in self.diyet_turleri]
            diet = None
            if seviye is not None:
                diet, _ = get_recommendation(seviye, semptoms)

            if diet:
                self.info_label.config(
                    text=f"Sistem tarafından {diet} öneriliyor.",
                    font=("Segoe UI", 11, "bold"),
                    fg="#8B5E3C",
                    anchor="center",
                    justify="center"
                )
            else:
                self.info_label.config(text="", font=("Segoe UI", 11, "italic"), fg="#595959", anchor="center", justify="center")


            self.diyet_menu['values'] = all_diets
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
            dt = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S")
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
class DataViewFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        card = tk.Frame(self, bg="#eaf6fb", bd=0, relief="flat", padx=40, pady=24)
        card.pack(pady=28)
        tk.Label(
            card,
            text="Doktor — Veri Görüntüle",
            font=("Arial", 20, "bold"),
            bg="#eaf6fb",
            fg="#232946",
        ).pack(pady=(0, 16), padx=8)
        frm = tk.Frame(card, bg="#eaf6fb")
        frm.pack(pady=8, padx=8)
        tk.Label(frm, text="Tablo Seçin:", font=("Segoe UI", 12, "bold"),
                 bg="#eaf6fb", anchor="e", width=16).grid(row=0, column=0, padx=(0,10), pady=3)
        self.tbl_var = tk.StringVar(value="tbl_olcum")
        opts = ['tbl_olcum', 'tbl_semptom', 'tbl_egzersiz_oneri', 'tbl_diyet_plani', 'doktor_kan_olcum']
        self.tbl_menu = ttk.Combobox(frm, textvariable=self.tbl_var, values=opts,
                                     font=("Segoe UI", 12), state="readonly", width=22)
        self.tbl_menu.grid(row=0, column=1, pady=3, sticky="w")
        bf = tk.Frame(card, bg="#eaf6fb")
        bf.pack(pady=14)
        ttk.Button(bf, text="Göster", style="Modern.TButton", command=self.show_data, width=14).pack(side="left", padx=8)
        ttk.Button(bf, text="Geri",    style="Modern.TButton", command=controller.go_back, width=14).pack(side="right", padx=8)

        self.tree = None
        self.tree_scroll = None
        
    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img) 

    def show_data(self):
        tbl = self.tbl_var.get()
        tc  = self.controller.frames["DoctorFrame"].patient_var.get()
        if self.tree:
            self.tree.destroy()
            self.tree_scroll.destroy()

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()
        if tbl == "tbl_semptom":
            query = """
                SELECT ts.tarih_saat, st.tur AS 'Semptom İsmi', ts.aciklama
                FROM tbl_semptom ts
                LEFT JOIN semptom_turleri st ON ts.semptom_tur_id = st.id
                WHERE ts.hasta_tc=%s
                ORDER BY ts.tarih_saat DESC
            """
            columns = ["Tarih Saat", "Semptom İsmi", "Açıklama"]

        elif tbl == "tbl_egzersiz_oneri":
            query = """
                SELECT te.tarih_saat, et.tur AS 'Egzersiz İsmi'
                FROM tbl_egzersiz_oneri te
                LEFT JOIN egzersiz_turleri et ON te.egzersiz_tur_id = et.id
                WHERE te.hasta_tc=%s
                ORDER BY te.tarih_saat DESC
            """
            columns = ["Tarih Saat", "Egzersiz İsmi"]

        elif tbl == "tbl_diyet_plani":
            query = """
                SELECT td.tarih_saat, dt.tur AS 'Diyet İsmi'
                FROM tbl_diyet_plani td
                LEFT JOIN diyet_turleri dt ON td.diyet_tur_id = dt.id
                WHERE td.hasta_tc=%s
                ORDER BY td.tarih_saat DESC
            """
            columns = ["Tarih Saat", "Diyet İsmi"]

        elif tbl == "doktor_kan_olcum":
            query = """
                SELECT tarih_saat, seviye_mgdl
                FROM doktor_kan_olcum
                WHERE hasta_tc=%s
                ORDER BY tarih_saat DESC
            """
            columns = ["Tarih Saat", "Seviye (mg/dl)"]

        else: 
            query = """
                SELECT tarih_saat AS 'Tarih Saat',
                       seviye_mgdl AS 'Seviye (mg/dl)',
                       tur       AS 'Ölçüm Türü'
                FROM tbl_olcum
                WHERE hasta_tc=%s
                ORDER BY tarih_saat DESC
            """
            columns = ["Tarih Saat", "Seviye (mg/dl)", "Ölçüm Türü"]
        cur.execute(query, (tc,))
        raw = cur.fetchall()
        cur.close()
        conn.close()
        formatted = []
        for row in raw:
            ts = row[0]
            if hasattr(ts, 'strftime'):
                ts_str = ts.strftime("%d.%m.%Y %H:%M:%S")
            else:
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    ts_str = dt.strftime("%d.%m.%Y %H:%M:%S")
                except:
                    ts_str = ts
            formatted.append((ts_str, *row[1:]))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview.Heading", font=("Arial", 11, "bold"))
        style.configure("Treeview", font=("Arial", 10), rowheight=24)
        style.map('Treeview', background=[('selected', '#ace3fc')])
        style.configure("evenrow", background="white")
        style.configure("oddrow",  background="#e2ecf7")

        self.tree_scroll = tk.Scrollbar(self)
        self.tree_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            yscrollcommand=self.tree_scroll.set,
            selectmode="browse"
        )
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center")
        for i, row in enumerate(formatted):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.tree.insert("", "end", values=row, tags=(tag,))
        self.tree.pack(pady=10, padx=10, fill="both", expand=True)
        self.tree_scroll.config(command=self.tree.yview)
class PatientFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg_path = "background.png"
        self.bg_img_raw = Image.open(bg_path)
        self.bg_img = None
        self.bg_label = tk.Label(self)
        self.bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_label.lower()
        self.bind("<Configure>", self._resize_bg)
        top_card = tk.Frame(self, bg="#f4f6fb")
        top_card.pack(pady=28)

        self.photo_label = tk.Label(top_card, bg="#f4f6fb", bd=0)
        self.photo_label.pack(side="left", padx=24)

        self.header = tk.Label(
            top_card,
            font=("Arial", 21, "bold"),
            bg="#f4f6fb",
            fg="#252a34"
        )
        self.header.pack(side="left", padx=(0, 18))
        info = (
            "Buradan günlük kan şekeri ölçümü, egzersiz takibi, "
            "diyet takibi ve belirti takibini yapabilirsiniz."
        )
        tk.Label(
            self,
            text=info,
            wraplength=680,
            font=("Arial", 12),
            bg="#f4f6fb"
        ).pack(pady=8)
        btn_card = tk.Frame(self, bg="#f4f6fb")
        btn_card.pack(pady=36)

        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=12,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )

        buttons = [
            ("Kan Şekeri Girişi",  "OlcumEntryFrame"),
            ("Egzersiz Takip",     "EgzersizTakipFrame"),
            ("Diyet Takip",        "DiyetTakipFrame"),
            ("Belirti Takip",      "PatientSymptomEntryFrame"),
            ("Günlük Ortalama",    "PatientGraphFrame"),
            ("İnsülin Takip",      "InsulinViewFrame"),
        ]
        for idx, (label, frame_name) in enumerate(buttons):
            row, col = divmod(idx, 3)
            btn = ttk.Button(
                btn_card,
                text=label,
                style="Modern.TButton",
                width=18,
                command=lambda f=frame_name: controller.show_frame(f)
            )
            btn.grid(row=row, column=col, padx=18, pady=14, sticky="ew")
        nav = tk.Frame(self, bg="#f4f6fb")
        nav.pack(side="bottom", fill="x", pady=16)
        ttk.Button(
            nav, text="Geri",
            style="Modern.TButton",
            command=controller.go_back
        ).pack(side="left", padx=35)
        ttk.Button(
            nav, text="Çıkış",
            style="Modern.TButton",
            command=controller.destroy
        ).pack(side="right", padx=35)

    def _resize_bg(self, event):
        w, h = event.width, event.height
        img = self.bg_img_raw.resize((max(w,1), max(h,1)), Image.LANCZOS)
        self.bg_img = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_img)

    def tkraise(self, above=None):
        self.header.config(text=f"{self.controller.current_user_name}, hoşgeldiniz.")

        patient_tc = self.controller.current_user_tc 
        photo_path = self.get_patient_photo_path(patient_tc)
        if photo_path:
            try:
                img = Image.open(photo_path).resize((86, 86))
                photo = ImageTk.PhotoImage(img)
                self.photo_label.config(image=photo)
                self.photo_label.image = photo
            except Exception as e:
                print(f"Fotoğraf yüklenemedi: {e}")

        super().tkraise(above)

    def get_patient_photo_path(self, tc):
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
class OlcumEntryFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        card = tk.Frame(self, bg="#eaf6fb", bd=0)
        card.pack(pady=38, padx=10, anchor="n")
        tk.Label(card, text="Kan Şekeri Girişi",
                 font=("Arial", 18, "bold"),
                 bg="#eaf6fb", fg="#252a34").pack(pady=(10, 18))
        form = tk.Frame(card, bg="#eaf6fb")
        form.pack(padx=14, pady=6)
        tk.Label(form, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):",
                 bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 anchor="e", width=27).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="e")
        self.tarih = ttk.Entry(form, font=("Segoe UI", 12), width=28)
        self.tarih.grid(row=0, column=1, padx=(0, 8), pady=10, sticky="w")
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        ttk.Button(form, text="Gün Sonu", style="Accent.TButton", command=self.end_of_day)\
            .grid(row=0, column=2, padx=(0, 8), pady=10, sticky="w")
        tk.Label(form, text="Seviye (mg/dL):",
                 bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 anchor="e", width=27).grid(row=1, column=0, padx=(0, 8), pady=10, sticky="e")
        self.seviye = ttk.Entry(form, font=("Segoe UI", 12), width=28)
        self.seviye.grid(row=1, column=1, padx=(0, 8), pady=10, sticky="w")
        tk.Label(form, text="Tür:",
                 bg="#eaf6fb", font=("Segoe UI", 12, "bold"),
                 anchor="e", width=27).grid(row=2, column=0, padx=(0, 8), pady=10, sticky="e")
        self.tur_var = tk.StringVar(value="Sabah")
        ttk.OptionMenu(form, self.tur_var, "Sabah", 'Sabah', 'Öğle', 'İkindi', 'Akşam', 'Gece')\
            .grid(row=2, column=1, padx=(0, 8), pady=10, sticky="w")
        btnf = tk.Frame(card, bg="#eaf6fb")
        btnf.pack(pady=(20, 8))
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=12,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )
        ttk.Button(btnf, text="Kaydet", width=14, style="Modern.TButton",
                   command=self.save).pack(side="left", padx=16)
        ttk.Button(btnf, text="Geri", width=14, style="Modern.TButton",
                   command=controller.go_back).pack(side="left", padx=16)
        self.msg_area = tk.Message(
            card,
            text="",
            width=520,
            bg="#eaf6fb",
            font=("Segoe UI", 11),
            justify="left"
        )
        self.msg_area.pack(pady=(12, 4), padx=10)

    def save(self):
        self.msg_area.config(text="")
        messages = []

        tc = self.controller.current_user_tc
        tr_input = self.tarih.get().strip() 
        try:
            sv = int(self.seviye.get())
        except ValueError:
            messagebox.showerror("Hata", "Seviye sayısal olmalı.")
            return
        tur = self.tur_var.get()

        try:
            dt_local = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                       .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            tr_mysql = dt_local.strftime("%Y-%m-%d %H:%M:%S")

            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor(buffered=True)
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
            cur.execute(
                "INSERT INTO tbl_olcum (hasta_tc, tarih_saat, seviye_mgdl, tur) "
                "VALUES (%s, %s, %s, %s)",
                (tc, tr_mysql, sv, tur)
            )
            if sv < 70:
                durum, uyarı_tipi, mesaj = (
                    "Hipoglisemi Riski",
                    "Acil Uyarı",
                    "Hastanın kan şekeri seviyesi 70 mg/dL'nin altına düştü. Hipoglisemi riski! Hızlı müdahale gerekebilir."
                )
            elif sv <= 110:
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
            start_new, end_new = VALID_WINDOWS[tur]
            if not (start_new <= dt_local.time() <= end_new):
                msg2 = "Ölçüm zamanı aralık dışında; ortalamaya dahil edilmeyecek."
                messages.append(msg2)
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
            if len(valid) < 3:
                msg3 = "Yetersiz veri! Ortalama hesaplaması güvenilir değildir."
                messages.append(msg3)
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
            conn.commit()
            cur.close()
            conn.close()
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
        dt_local = datetime.strptime(tr_input, "%d.%m.%Y %H:%M:%S") \
                         .replace(tzinfo=ZoneInfo("Europe/Istanbul"))
        tr_mysql = dt_local.strftime("%Y-%m-%d %H:%M:%S")

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()
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
            conn.close()
            messagebox.showinfo("Gün Sonu", "Bugün için yeterli ölçüm var, uyarı oluşturulmadı.")
            return
        cur.execute(
            "INSERT INTO uyarilar (hasta_tc, tarih_saat, durum, uyarı_tipi, mesaj) "
            "VALUES (%s, %s, %s, %s, %s)",
            (tc, tr_mysql, durum, uyarı_tipi, mesaj)
        )
        conn.commit()
        cur.close()
        conn.close()

        messagebox.showinfo("Gün Sonu Uyarısı", mesaj)
class EgzersizTakipFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(self, text="Egzersiz Uyum Takibi",
                 font=("Segoe UI", 19, "bold"), bg="white", fg="#252a34")\
          .pack(pady=(20, 8))
        self.doktor_onerisi_label = tk.Label(self, text="", font=("Segoe UI", 12, "bold"), bg="white", fg="#a05710")
        self.doktor_onerisi_label.pack(pady=(0, 10))
        form = tk.Frame(self, bg="white")
        form.pack(pady=5)

        tk.Label(form, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="e", padx=5, pady=6)
        self.tarih = tk.Entry(form, width=28, font=("Segoe UI", 12))
        self.tarih.grid(row=0, column=1, pady=6)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        self.yap_var = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text="Yapıldı", variable=self.yap_var, bg="white", font=("Segoe UI", 11)).grid(row=1, column=1, sticky="w", pady=2)
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=16)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )
        ttk.Button(btnf, text="Kaydet", style="Modern.TButton", width=14, command=self.save).pack(side="left", padx=12)
        ttk.Button(btnf, text="Geri", style="Modern.TButton", width=14, command=controller.go_back).pack(side="left", padx=12)
        self.summary_label = tk.Label(self, text="", font=("Segoe UI", 12), bg="white", fg="#252a34")
        self.summary_label.pack(pady=(2, 10))
        cols = ("tarih", "durum")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=6)
        self.tree.heading("tarih", text="Tarih/Saat", anchor="center")
        self.tree.heading("durum",  text="Egzersiz Durumu", anchor="center")
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
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(self, text="Diyet Uyum Takibi",
                 font=("Segoe UI", 19, "bold"), bg="white", fg="#252a34")\
          .pack(pady=(20, 8))
        self.doktor_onerisi_label = tk.Label(self, text="", font=("Segoe UI", 12, "bold"), bg="white", fg="#a05710")
        self.doktor_onerisi_label.pack(pady=(0, 10))
        form = tk.Frame(self, bg="white")
        form.pack(pady=5)

        tk.Label(form, text="Tarih/Saat (DD.MM.YYYY HH:MM:SS):", bg="white", font=("Segoe UI", 12, "bold"))\
          .grid(row=0, column=0, sticky="e", padx=5, pady=6)
        self.tarih = tk.Entry(form, width=28, font=("Segoe UI", 12))
        self.tarih.grid(row=0, column=1, pady=6)
        self.tarih.insert(0, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        self.uyg_var = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text="Uygulandı", variable=self.uyg_var, bg="white", font=("Segoe UI", 11)).grid(row=1, column=1, sticky="w", pady=2)
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=16)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )
        ttk.Button(btnf, text="Kaydet", style="Modern.TButton", width=14, command=self.save).pack(side="left", padx=12)
        ttk.Button(btnf, text="Geri", style="Modern.TButton", width=14, command=controller.go_back).pack(side="left", padx=12)
        self.summary_label = tk.Label(self, text="", font=("Segoe UI", 12), bg="white", fg="#252a34")
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
class PatientSymptomEntryFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(
            self, text="Doktor Teşhis Geçmişi",
            font=("Segoe UI", 19, "bold"),
            bg="white", fg="#252a34"
        ).pack(pady=(28, 14))
        card = tk.Frame(self, bg="#f4f6fb", bd=0, relief="groove")
        card.pack(fill="both", expand=True, padx=30, pady=(0, 10))
        style = ttk.Style()
        style.configure(
            "Modern.Treeview",
            font=("Segoe UI", 11),
            rowheight=32,
            background="#ffffff",
            fieldbackground="#ffffff",
        )
        style.configure(
            "Modern.Treeview.Heading",
            font=("Segoe UI", 12, "bold"),
            background="#cfe2f3",
            foreground="#2d3142"
        )
        style.map("Modern.Treeview", background=[('selected', '#e3eeff')])
        style.configure("evenrow", background="#e6f2ff")  
        style.configure("oddrow", background="#ffffff")   

        self.tree = ttk.Treeview(
            card, columns=("tarih", "semptom", "aciklama"),
            show="headings", style="Modern.Treeview", selectmode="none", height=12
        )
        self.tree.heading("tarih", text="Tarih/Saat")
        self.tree.heading("semptom", text="Semptom İsmi")
        self.tree.heading("aciklama", text="Doktor Açıklaması")
        self.tree.column("tarih", anchor="center", width=165)
        self.tree.column("semptom", anchor="center", width=170)
        self.tree.column("aciklama", anchor="w", width=370, stretch=True)
        self.tree.pack(fill="both", expand=True, padx=12, pady=(10, 8))
        btnf = tk.Frame(self, bg="#f4f6fb")
        btnf.pack(fill="x", padx=36, pady=(4, 14))
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#fff",
            foreground="#222e44",
            borderwidth=0
        )
        style.map("Modern.TButton",
                  background=[('active', '#e3eeff'), ('!active', '#fff')],
                  foreground=[('active', '#1d4e89'), ('!active', '#222e44')])
        ttk.Button(
            btnf, text="Geri", style="Modern.TButton",
            width=16, command=controller.go_back
        ).pack(side="left", padx=4, pady=2)

    def tkraise(self, above=None):
        self.show_all_diagnoses()
        super().tkraise(above)

    def show_all_diagnoses(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            tc = self.controller.current_user_tc
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
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
                for idx, (tarih_saat, semptom_ismi, aciklama) in enumerate(results):
                    tag = "evenrow" if idx % 2 == 0 else "oddrow"
                    self.tree.insert(
                        "", "end",
                        values=(
                            tarih_saat.strftime("%d.%m.%Y %H:%M:%S") if hasattr(tarih_saat, 'strftime') else str(tarih_saat),
                            semptom_ismi,
                            aciklama
                        ),
                        tags=(tag,)
                    )
            else:
                self.tree.insert(
                    "", "end",
                    values=("", "Teşhis Yok", "Doktorunuz tarafından henüz teşhis konmamıştır."),
                    tags=("evenrow",)
                )

        except Exception as e:
            self.tree.insert(
                "", "end",
                values=("", "Hata", "Teşhis bilgileri alınamadı."),
                tags=("evenrow",)
            )
            print(f"Hata: {e}")



class DoctorFilterFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        bg = tk.Label(self, image=controller.bg_image)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        card = tk.Frame(self, bg="#eaf6fb", bd=2, relief="groove")
        card.pack(pady=50, padx=10)
        tk.Label(card, text="Doktor — Hastaları Filtrele",
                 font=("Segoe UI", 18, "bold"),
                 bg="#eaf6fb", fg="#1d2439").pack(pady=(18, 12))
        frm = tk.Frame(card, bg="#eaf6fb")
        frm.pack(padx=30, pady=5)
        ttk.Label(frm, text="Min Seviye (mg/dL):", background="#eaf6fb", font=("Segoe UI", 12, "bold"), width=20).grid(row=0, column=0, padx=6, pady=8, sticky="e")
        self.min_entry = ttk.Entry(frm, width=18, font=("Segoe UI", 12))
        self.min_entry.grid(row=0, column=1, padx=6, pady=8)

        ttk.Label(frm, text="Max Seviye (mg/dL):", background="#eaf6fb", font=("Segoe UI", 12, "bold"), width=20).grid(row=1, column=0, padx=6, pady=8, sticky="e")
        self.max_entry = ttk.Entry(frm, width=18, font=("Segoe UI", 12))
        self.max_entry.grid(row=1, column=1, padx=6, pady=8)

        ttk.Label(frm, text="Belirti:", background="#eaf6fb", font=("Segoe UI", 12, "bold"), width=20).grid(row=2, column=0, padx=6, pady=8, sticky="e")
        self.symptom_var = tk.StringVar(value="")
        symptoms = [""] + self._load_symptoms()
        self.symptom_menu = ttk.Combobox(frm, textvariable=self.symptom_var, values=symptoms, state="readonly", width=16, font=("Segoe UI", 12))
        self.symptom_menu.grid(row=2, column=1, padx=6, pady=8)
        btnf = tk.Frame(frm, bg="#eaf6fb")
        btnf.grid(row=4, column=0, columnspan=2, pady=18)
        ttk.Style().configure("Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=8,
            foreground="#222e44",
            background="#fff"
        )
        ttk.Button(
            btnf, text="Filtrele",
            style="Modern.TButton",
            command=self.filter,
            width=14
        ).pack(side="left", padx=18)
        ttk.Button(
            btnf, text="Geri",
            style="Modern.TButton",
            command=controller.go_back,
            width=14
        ).pack(side="left", padx=18)
        cols = ("tc", "isim", "tarih", "tip", "deger")
        style = ttk.Style()
        style.configure("Custom.Treeview.Heading", font=("Segoe UI", 11, "bold"))
        style.configure("Custom.Treeview", font=("Segoe UI", 11), rowheight=26, borderwidth=0)
        style.map('Custom.Treeview', background=[('selected', '#ace3fc')])

        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=12, style="Custom.Treeview")
        for c, w in zip(cols, [120, 150, 160, 100, 100]):
            self.tree.heading(c, text=c.upper(), anchor="center")
            self.tree.column(c, anchor="center", width=w)
        self.tree.pack(padx=10, pady=(10, 24), fill="both", expand=True)



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
        for item in self.tree.get_children():
            self.tree.delete(item)

        tc_doc  = self.controller.current_user_tc
        min_v   = self.min_entry.get().strip()
        max_v   = self.max_entry.get().strip()
        symptom = self.symptom_var.get().strip()

        conn = mysql.connector.connect(**DB_CONFIG)
        cur  = conn.cursor()

        records = []
        if not (min_v or max_v or symptom):
            cur.execute("""
                SELECT h.kullanici_adi,
                       h.isim,
                       o.tarih_saat,
                       'Kan Şekeri' AS tip,
                       o.seviye_mgdl
                FROM hasta h
                JOIN tbl_olcum o ON h.kullanici_adi = o.hasta_tc
                WHERE h.doktor_tc = %s
            """, (tc_doc,))
            records += cur.fetchall()
            cur.execute("""
                SELECT h.kullanici_adi,
                       h.isim,
                       s.tarih_saat,
                       'Belirti' AS tip,
                       st.tur AS deger
                FROM hasta h
                JOIN tbl_semptom s ON h.kullanici_adi = s.hasta_tc
                JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                WHERE h.doktor_tc = %s
            """, (tc_doc,))
            records += cur.fetchall()
            cur.execute("""
                SELECT h.kullanici_adi,
                       h.isim,
                       d.tarih_saat,
                       'Kan Şekeri' AS tip,
                       d.seviye_mgdl
                FROM hasta h
                JOIN doktor_kan_olcum d ON h.kullanici_adi = d.hasta_tc
                WHERE h.doktor_tc = %s
            """, (tc_doc,))
            records += cur.fetchall()

        else:
            if min_v and max_v:
                try:
                    mn, mx = int(min_v), int(max_v)
                    cur.execute("""
                        SELECT h.kullanici_adi,
                               h.isim,
                               o.tarih_saat,
                               'Kan Şekeri' AS tip,
                               o.seviye_mgdl
                        FROM hasta h
                        JOIN tbl_olcum o ON h.kullanici_adi = o.hasta_tc
                        WHERE h.doktor_tc = %s
                          AND o.seviye_mgdl BETWEEN %s AND %s
                    """, (tc_doc, mn, mx))
                    records += cur.fetchall()
                    cur.execute("""
                        SELECT h.kullanici_adi,
                               h.isim,
                               d.tarih_saat,
                               'Kan Şekeri' AS tip,
                               d.seviye_mgdl
                        FROM hasta h
                        JOIN doktor_kan_olcum d ON h.kullanici_adi = d.hasta_tc
                        WHERE h.doktor_tc = %s
                          AND d.seviye_mgdl BETWEEN %s AND %s
                    """, (tc_doc, mn, mx))
                    records += cur.fetchall()

                except ValueError:
                    messagebox.showerror("Hata", "Min/Max seviye sayısal olmalı.")
            if symptom:
                cur.execute("""
                    SELECT h.kullanici_adi,
                           h.isim,
                           s.tarih_saat,
                           'Belirti' AS tip,
                           st.tur AS deger
                    FROM hasta h
                    JOIN tbl_semptom s ON h.kullanici_adi = s.hasta_tc
                    JOIN semptom_turleri st ON s.semptom_tur_id = st.id
                    WHERE h.doktor_tc = %s
                      AND st.tur = %s
                """, (tc_doc, symptom))
                records += cur.fetchall()

        cur.close()
        conn.close()
        records.sort(key=lambda r: r[2], reverse=True)
        for tc, isim, ts, tip, val in records:
            t_str = ts.strftime("%d.%m.%Y %H:%M:%S") if hasattr(ts, 'strftime') else str(ts)
            self.tree.insert("", "end", values=(tc, isim, t_str, tip, val))


   
class DoctorGraphFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        card = tk.Frame(self, bg="#f4f6fb", bd=0, relief="flat")
        card.pack(pady=40, padx=0, fill="x")
        title = tk.Label(
            card,
            text="Doktor — Grafikler",
            font=("Segoe UI", 22, "bold"),
            bg="#f4f6fb",
            fg="#262b37"
        )
        title.pack(pady=(18, 32))
        btnf = tk.Frame(card, bg="#f4f6fb")
        btnf.pack(pady=4)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 13, "bold"),
            padding=18,
            background="#fff",
            foreground="#252a34",
            borderwidth=0,
            relief="flat"
        )
        style.map("Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#252a34')]
        )
        ttk.Button(
            btnf,
            text="Kan Şekeri & Diyet/Egzersiz",
            style="Modern.TButton",
            command=self.plot_glucose_diet_ex,
            width=28
        ).pack(side="left", padx=22)

        ttk.Button(
            btnf,
            text="Egzersiz/Diyet Uyum Oranları",
            style="Modern.TButton",
            command=self.plot_ex_diet,
            width=28
        ).pack(side="left", padx=22)
        ttk.Button(
            btnf,
            text="Egzersiz/Diyet Geçmişi",
            style="Modern.TButton",
            command=self.show_ex_diet_history,
            width=28
        ).pack(side="left", padx=22)

        ttk.Button(
            btnf,
            text="Geri",
            style="Modern.TButton",
            command=controller.go_back,
            width=16
        ).pack(side="left", padx=22)
        self.canvas = None
        self.tree = None

    def _clear_canvas(self):
        """Önceki grafiği veya tabloyu temizle."""
        if self.canvas:
            self.canvas.get_tk_widget().pack_forget()
            plt.close('all')
            self.canvas = None
        if self.tree:
            self.tree.destroy()
            self.tree = None

    def _draw(self, fig):
        """Yeni matplotlib figürünü ekrana çiz."""
        self._clear_canvas()
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def plot_ex_diet(self):
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tbl_egzersiz_takip WHERE hasta_tc=%s", (tc,))
        total_ex = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT COUNT(*) FROM tbl_egzersiz_takip WHERE hasta_tc=%s AND yapilan_egzersiz NOT LIKE 'Egzersiz yapılmadı'", (tc,))
        done_ex = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT COUNT(*) FROM tbl_diyet_takip WHERE hasta_tc=%s", (tc,))
        total_di = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT COUNT(*) FROM tbl_diyet_takip WHERE hasta_tc=%s AND uygulanan_diyet NOT LIKE 'Diyet uygulanmadı'", (tc,))
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
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT tarih_saat, seviye_mgdl "
            "FROM tbl_olcum "
            "WHERE hasta_tc=%s "
            "ORDER BY tarih_saat",
            (tc,)
        )
        glucose = cur.fetchall()
        cur.execute(
            "SELECT tarih_saat FROM tbl_egzersiz_takip "
            "WHERE hasta_tc=%s ORDER BY tarih_saat",
            (tc,)
        )
        ex_times = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT tarih_saat FROM tbl_diyet_takip "
            "WHERE hasta_tc=%s ORDER BY tarih_saat",
            (tc,)
        )
        di_times = [r[0] for r in cur.fetchall()]

        cur.close()
        conn.close()

        if not glucose:
            messagebox.showinfo("Bilgi", "Herhangi bir ölçüm bulunamadı.")
            return

        times, values = zip(*glucose)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(times, values, marker='o', linestyle='-', label='Glukoz')
        if ex_times:
            ax.vlines(ex_times,
                      ymin=min(values), ymax=max(values),
                      colors='red', linestyles='--',
                      label='Egzersiz')
        if di_times:
            ax.vlines(di_times,
                      ymin=min(values), ymax=max(values),
                      colors='green', linestyles='-.' ,
                      label='Diyet')
        ax.set_title("Gün Boyu Glukoz & Egzersiz/Diyet Etkisi", fontsize=14, pad=12)
        ax.set_xlabel("Tarih/Saat", fontsize=12, labelpad=8)
        ax.set_ylabel("Kan Şekeri (mg/dL)", fontsize=12, labelpad=8)
        ax.grid(True, linestyle=':', linewidth=0.5)
        ax.legend(loc='upper left', frameon=False, fontsize=10)
        ax.xaxis.set_major_formatter(DateFormatter("%d.%m\n%H:%M"))
        fig.autofmt_xdate()
        self._draw(fig)

    def show_ex_diet_history(self):
        """Egzersiz ve diyet geçmişini tablo olarak gösterir."""
        self._clear_canvas()
        tc = self.controller.frames["DoctorFrame"].patient_var.get()
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT tarih_saat, yapilan_egzersiz FROM tbl_egzersiz_takip WHERE hasta_tc=%s ORDER BY tarih_saat",
            (tc,)
        )
        ex_rows = cur.fetchall()
        cur.execute(
            "SELECT tarih_saat, uygulanan_diyet FROM tbl_diyet_takip WHERE hasta_tc=%s ORDER BY tarih_saat",
            (tc,)
        )
        di_rows = cur.fetchall()
        cur.close(); conn.close()
        combined = [(ts, 'Egzersiz', val) for ts, val in ex_rows] + [(ts, 'Diyet', val) for ts, val in di_rows]
        combined.sort(key=lambda x: x[0])
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Modern.Treeview",
            font=("Segoe UI", 11),
            rowheight=26,
            background="#ffffff",
            fieldbackground="#ffffff",
            bordercolor="#ddd",
            borderwidth=1
        )
        style.configure(
            "Modern.Treeview.Heading",
            font=("Segoe UI", 12, "bold"),
            background="#f0f0f0",
            foreground="#333"
        )
        style.map(
            "Modern.Treeview",
            background=[('selected', '#ace3fc')]
        )
        style.configure("evenrow", background="#e2ecf7")
        style.configure("oddrow",  background="#ffffff")
        self.tree = ttk.Treeview(
            self,
            columns=("tarih", "tip", "durum"),
            show="headings",
            style="Modern.Treeview"
        )
        self.tree.heading("tarih", text="Tarih/Saat")
        self.tree.heading("tip", text="Tip")
        self.tree.heading("durum", text="Durum")
        self.tree.column("tarih", anchor="center", width=180)
        self.tree.column("tip", anchor="center",  width=100)
        self.tree.column("durum", anchor="w",       width=260)
        for idx, (ts, tip, durum) in enumerate(combined):
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            t_str = ts.strftime("%d.%m.%Y %H:%M:%S") if hasattr(ts, 'strftime') else str(ts)
            self.tree.insert("", "end", values=(t_str, tip, durum), tags=(tag,))

        self.tree.pack(fill="both", expand=True, padx=20, pady=10)


class PatientGraphFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        tk.Label(self, text="Günlük Kan Şekeri Değerleri", font=("Segoe UI", 19, "bold"), bg="white", fg="#252a34").pack(pady=18)
        btnf = tk.Frame(self, bg="white")
        btnf.pack(pady=10)
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#fff",
            foreground="#222e44",
            borderwidth=2,
            relief="solid" 
        )
        style.map("Modern.TButton",
                  background=[('active', '#e3eeff'), ('!active', '#fff')],
                  foreground=[('active', '#1d4e89'), ('!active', '#222e44')])
        tk.Label(btnf, text="Tarih (GG.AA.YYYY):", font=("Segoe UI", 11, "bold"), bg="white", fg="#444").pack(side="left", padx=7)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%d.%m.%Y"))
        self.date_entry = tk.Entry(btnf, textvariable=self.date_var, width=12, font=("Segoe UI", 11))
        self.date_entry.pack(side="left", padx=7)
        ttk.Button(btnf, text="Tarihe Göre Grafik Göster", style="Modern.TButton", width=22, command=self.plot_for_selected).pack(side="left", padx=7)
        ttk.Button(btnf, text="Kayıtlı Ölçümler ve Günlük Ortalamalar", style="Modern.TButton", width=28, command=self.show_tables).pack(side="left", padx=7)
        ttk.Button(btnf, text="Yenile", style="Modern.TButton", width=13, command=self.refresh_current).pack(side="left", padx=7)
        ttk.Button(btnf, text="Geri", style="Modern.TButton", width=13, command=controller.go_back).pack(side="left", padx=7)
        self.canvas = None
        self.table = None
        self.mode = 'daily'

    def tkraise(self, above=None):
        super().tkraise(above)
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
        cur.execute(
            "SELECT DATE_FORMAT(tarih_saat, '%d.%m.%Y %H:%i'), seviye_mgdl "
            "FROM tbl_olcum "
            "WHERE hasta_tc=%s "
            "ORDER BY tarih_saat",
            (tc,)
        )
        measurements = cur.fetchall()
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
        self.table = ttk.Treeview(self, columns=("col1","col2"), show="headings", height=20)
        self.table.heading("col1", text="Zaman")
        self.table.heading("col2", text="Değer / Ortalama")
        self.table.column("col1", anchor="center", width=200)
        self.table.column("col2", anchor="center", width=200)
        self.table.insert("", "end", values=("=== Tüm Kayıtlı Ölçümler ===",""))
        for i, (zaman, deger) in enumerate(measurements):
            tag = 'even' if i % 2 == 0 else 'odd'
            self.table.insert("", "end", values=(zaman, deger), tags=(tag,))
        self.table.insert("", "end", values=("=== Günlük Ortalamalar ===",""))
        for j, (tarih, ort) in enumerate(averages):
            tag = 'even' if j % 2 == 0 else 'odd'
            self.table.insert("", "end", values=(tarih.strftime("%d.%m.%Y"), ort), tags=(tag,))
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

        kahve_bg = "#f6eee3" 
        self.configure(bg=kahve_bg)
        tk.Label(self, text="İnsülin Takip",
                 font=("Segoe UI", 19, "bold"),
                 bg=kahve_bg, fg="#252a34")\
          .pack(pady=18)
        frm = tk.Frame(self, bg=kahve_bg)
        frm.pack(pady=5)
        style = ttk.Style()
        style.configure(
            "ModernBrown.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#fff",
            foreground="#2e1300",
            borderwidth=2,
            relief="solid"
        )
        style.map("ModernBrown.TButton",
            background=[('active', '#ead7c3'), ('!active', '#fff')],
            foreground=[('active', '#3d1602'), ('!active', '#2e1300')],
            bordercolor=[('active', '#000'), ('!active', '#000')]
        )
        tk.Label(frm, text="Tarih (DD.MM.YYYY):",
                 bg=kahve_bg, font=("Segoe UI", 11, "bold"), fg="#444")\
          .grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.date_entry = tk.Entry(frm, width=12, font=("Segoe UI", 11))
        self.date_entry.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Button(frm, text="O Günün Kayıtları",
                   style="ModernBrown.TButton", width=18,
                   command=self.show_for_date)\
          .grid(row=0, column=2, padx=(18, 4), pady=4)
        tk.Label(frm, text="Başlangıç (DD.MM.YYYY):",
                 bg=kahve_bg, font=("Segoe UI", 11, "bold"), fg="#444")\
          .grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.start_entry = tk.Entry(frm, width=12, font=("Segoe UI", 11))
        self.start_entry.grid(row=1, column=1, sticky="w", pady=2)

        tk.Label(frm, text="Bitiş (DD.MM.YYYY):",
                 bg=kahve_bg, font=("Segoe UI", 11, "bold"), fg="#444")\
          .grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self.end_entry = tk.Entry(frm, width=12, font=("Segoe UI", 11))
        self.end_entry.grid(row=2, column=1, sticky="w", pady=2)

        ttk.Button(frm, text="Aralığa Göre Göster",
                   style="ModernBrown.TButton", width=18,
                   command=self.show_range)\
          .grid(row=1, column=2, rowspan=2, padx=(18, 4), pady=4)
        btnf = tk.Frame(self, bg=kahve_bg)
        btnf.pack(pady=14)
        ttk.Button(btnf, text="Geri",
                   style="ModernBrown.TButton", width=14,
                   command=controller.go_back).pack()
        self.tree = ttk.Treeview(self,
                                 columns=("tarih", "birim", "ogun"),
                                 show="headings", height=15)
        self.tree.heading("tarih", text="Tarih/Saat", anchor="center")
        self.tree.heading("birim", text="İnsülin (Birim)", anchor="center")
        self.tree.heading("ogun", text="Öğün", anchor="center")
        self.tree.column("tarih", width=200, anchor="center")
        self.tree.column("birim", width=140, anchor="center")
        self.tree.column("ogun", width=100, anchor="center")
        self.tree.pack(padx=20, pady=(10, 18), fill="x")
        self.tree.tag_configure("even", background="#ede2d6")
        self.tree.tag_configure("odd", background="#fff7ee")

    def fill_table(self, rows):
        """Treeview'i temizleyip yeni verileri ekler."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, (ts, birim, ogun) in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            tarih_str = ts.strftime('%d.%m.%Y %H:%M:%S') if hasattr(ts, 'strftime') else str(ts)
            self.tree.insert("", "end",
                             values=(tarih_str, birim, ogun or "-"),
                             tags=(tag,))

    def show_for_date(self):
        date_str = self.date_entry.get().strip()
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y")
            mysql_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Geçersiz Tarih", "Lütfen DD.MM.YYYY formatında girin.")
            return

        tc = self.controller.current_user_tc
        query = """
            SELECT 
                i.tarih_saat,
                i.birim_u,
                o.tur
            FROM tbl_insulin AS i
            LEFT JOIN tbl_olcum AS o
            ON i.hasta_tc   = o.hasta_tc
            AND i.tarih_saat = o.tarih_saat
            WHERE i.hasta_tc = %s
            AND DATE(i.tarih_saat) = %s
            ORDER BY i.tarih_saat DESC
        """
        params = (tc, mysql_date)
        self._run_and_display(query, params)

    def show_range(self):
        start_str = self.start_entry.get().strip()
        end_str = self.end_entry.get().strip()
        try:
            dt_start = datetime.strptime(start_str, "%d.%m.%Y")
            dt_end = datetime.strptime(end_str, "%d.%m.%Y")
            start_date = dt_start.strftime("%Y-%m-%d")
            end_date = dt_end.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Geçersiz Tarih",
                                 "Başlangıç ve Bitiş için DD.MM.YYYY formatını kullanın.")
            return

        tc = self.controller.current_user_tc
        query = """
            SELECT 
                i.tarih_saat,
                i.birim_u,
                o.tur
            FROM tbl_insulin AS i
            LEFT JOIN tbl_olcum AS o
            ON i.hasta_tc   = o.hasta_tc
            AND i.tarih_saat = o.tarih_saat
            WHERE i.hasta_tc = %s
            AND DATE(i.tarih_saat) BETWEEN %s AND %s
            ORDER BY i.tarih_saat DESC
        """
        params = (tc, start_date, end_date)
        self._run_and_display(query, params)

    def _run_and_display(self, query, params):
        """SQL sorgusunu çalıştırır, hatayı gösterir ya da sonuçları doldurur."""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
        except Exception as e:
            messagebox.showerror("Veri Hatası", str(e))
            return
        finally:
            cur.close()
            conn.close()

        self.fill_table(rows)


class UyariFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="white")
        style = ttk.Style()
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background="#fff",
            foreground="#222e44",
            borderwidth=1,
            relief="ridge"
        )
        style.map(
            "Modern.TButton",
            background=[('active', '#e3eeff'), ('!active', '#fff')],
            foreground=[('active', '#1d4e89'), ('!active', '#222e44')]
        )
        tk.Label(self,
                 text="Doktor — Uyarılar",
                 font=("Arial", 20, "bold"),
                 bg="white")\
          .pack(pady=10)
        patients = controller.get_my_patients() 
        options  = [tc for tc, _ in patients]
        self.patient_var = controller.frames["DoctorFrame"].patient_var
        if options:
            self.patient_var.set(options[0])
        ttk.OptionMenu(self,
                       self.patient_var,
                       self.patient_var.get(),
                       *options)\
           .pack(pady=5)
        self.acil_tv = ttk.Treeview(
            self,
            columns=("tarih_saat", "durum", "uyari_tipi", "mesaj"),
            show="headings",
            selectmode="none",
            height=8
        )
        vsb1 = ttk.Scrollbar(self,
                             orient="vertical",
                             command=self.acil_tv.yview)
        self.acil_tv.configure(yscrollcommand=vsb1.set)

        for col in ("tarih_saat", "durum", "uyari_tipi", "mesaj"):
            self.acil_tv.heading(col,
                                 text=col.replace("_", " ").title(),
                                 anchor="center")
            self.acil_tv.column(col,
                                anchor="w",
                                width=(150 if col!="mesaj" else 400))

        self.acil_tv.tag_configure("evenrow", background="#e6f2ff")
        self.acil_tv.tag_configure("oddrow",  background="white")

        tk.Label(self,
                 text="ACİL UYARILAR",
                 font=("Arial", 15, "bold"),
                 bg="white")\
          .pack(pady=(15,0), anchor="w", padx=10)

        self.acil_tv.pack(padx=10, pady=(0,5), fill="x")
        vsb1.place(in_=self.acil_tv, relx=1.0, rely=0, relheight=1.0)
        self.diger_tv = ttk.Treeview(
            self,
            columns=("tarih_saat", "durum", "uyari_tipi", "mesaj"),
            show="headings",
            selectmode="none",
            height=6
        )
        vsb2 = ttk.Scrollbar(self,
                             orient="vertical",
                             command=self.diger_tv.yview)
        self.diger_tv.configure(yscrollcommand=vsb2.set)

        for col in ("tarih_saat", "durum", "uyari_tipi", "mesaj"):
            self.diger_tv.heading(col,
                                  text=col.replace("_", " ").title(),
                                  anchor="w")
            self.diger_tv.column(col,
                                 anchor="w",
                                 width=(150 if col!="mesaj" else 400))

        self.diger_tv.tag_configure("evenrow", background="#e6f2ff")
        self.diger_tv.tag_configure("oddrow",  background="white")

        tk.Label(self,
                 text="DİĞER UYARILAR",
                 font=("Arial", 15, "bold"),
                 bg="white")\
          .pack(pady=(15,0), anchor="w", padx=10)

        self.diger_tv.pack(padx=10, pady=(0,5), fill="x")
        vsb2.place(in_=self.diger_tv, relx=1.0, rely=0, relheight=1.0)
        btnf = tk.Frame(self, bg="white")
        btnf.pack(side="bottom", fill="x", pady=10)

        ttk.Button(
            btnf,
            text="Yenile",
            width=15,
            style="Modern.TButton",
            command=self.load_warnings
        ).pack(side="left", padx=10, pady=2)

        ttk.Button(
            btnf,
            text="Geri",
            width=15,
            style="Modern.TButton",
            command=controller.go_back
        ).pack(side="right", padx=10, pady=2)

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
        for tv in (self.acil_tv, self.diger_tv):
            for iid in tv.get_children():
                tv.delete(iid)
        acil_rows  = [r for r in rows if r[2] == "Acil Uyarı"]
        diger_rows = [r for r in rows if r[2] != "Acil Uyarı"]

        for tv, data in ((self.acil_tv, acil_rows), (self.diger_tv, diger_rows)):
            for idx, (tarih, durum, tip, msg) in enumerate(data):
                tag = "evenrow" if idx % 2 == 0 else "oddrow"
                tv.insert("", "end",
                          values=(tarih, durum, tip, msg),
                          tags=(tag,))
if __name__ == "__main__":
    app = App()
    app.mainloop()
