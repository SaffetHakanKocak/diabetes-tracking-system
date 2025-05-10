import bcrypt
import mysql.connector
from config import DB_CONFIG, HASH_ROUNDS

def migrate_doctor_passwords():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT kullanici_adi, sifre FROM doktor")
    for tc, pw in cur.fetchall():
        # pw zaten bcrypt hash’ine başlıyorsa skip edelim
        if isinstance(pw, str) and pw.startswith("$2b$"):
            continue

        # pw plain-text ise hash’le
        pw_bytes = pw.encode("utf-8")
        new_hash = bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=HASH_ROUNDS))
        # DB’de VARCHAR(60) vs. bir kolonda saklıyorsak, string olarak yazın:
        cur.execute(
            "UPDATE doktor SET sifre=%s WHERE kullanici_adi=%s",
            (new_hash.decode("utf-8"), tc)
        )

    conn.commit()
    cur.close()
    conn.close()
    print("Doktor şifreleri başarıyla hash’lendi.")

if __name__ == "__main__":
    migrate_doctor_passwords()
