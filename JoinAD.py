import os
import socket
import ipaddress
import ctypes
import subprocess
import sys
from cryptography.fernet import Fernet
import json

# Κλειδί για κρυπτογράφηση
CONFIG_KEY = b""
CONFIG_FILE = "config.enc"

# Δημιουργία κλειδιού (μόνο για αρχική χρήση)
def generate_key():
    key = Fernet.generate_key()
    print(f"Κλειδί: {key}")
    return key

# Κρυπτογράφηση δεδομένων
def encrypt_data(data):
    cipher_suite = Fernet(CONFIG_KEY)
    return cipher_suite.encrypt(data.encode())

# Αποκρυπτογράφηση δεδομένων
def decrypt_data(data):
    cipher_suite = Fernet(CONFIG_KEY)
    return cipher_suite.decrypt(data).decode()

# Δημιουργία ή επεξεργασία αρχείου ρυθμίσεων
def create_or_edit_config():
    print("=== Δημιουργία/Επεξεργασία Αρχείου Ρυθμίσεων ===")
    config = {
        "AD_SERVER": input("Εισάγετε το LDAP URL (π.χ., ldap://172.18.XXX.XXX): ").strip(),
        "AD_USERNAME": input("Εισάγετε το όνομα χρήστη (π.χ., domainame\\admin): ").strip(),
        "AD_PASSWORD": input("Εισάγετε τον κωδικό πρόσβασης: ").strip(),
        "AD_BASE_DN": input("Εισάγετε το Base DN (π.χ., DC=domainame,DC=gr): ").strip(),
        "ALLOWED_SUBNETS": input("Εισάγετε τα επιτρεπόμενα υποδίκτυα, διαχωρισμένα με κόμμα (π.χ., 172.18.17.0/24,172.118.16.0/24): ").strip().split(","),
        "ALLOWED_USERS": input("Εισάγετε τους επιτρεπόμενους χρήστες, διαχωρισμένους με κόμμα (π.χ., admin,admininstrator): ").strip().split(","),
    }

    # Κρυπτογράφηση και αποθήκευση
    with open(CONFIG_FILE, "wb") as file:
        encrypted_data = encrypt_data(json.dumps(config))
        file.write(encrypted_data)
    print("Το αρχείο ρυθμίσεων δημιουργήθηκε/ενημερώθηκε επιτυχώς.")

# Φόρτωση ρυθμίσεων από το κρυπτογραφημένο αρχείο
def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("Το αρχείο ρυθμίσεων δεν βρέθηκε. Τρέξτε το script με την παράμετρο /newconf για να το δημιουργήσετε.")
        exit()

    with open(CONFIG_FILE, "rb") as file:
        encrypted_data = file.read()
        decrypted_data = decrypt_data(encrypted_data)
        return json.loads(decrypted_data)

# Λειτουργία για εύρεση της τρέχουσας IP
def get_current_ip():
    hostname = socket.gethostname()
    return socket.gethostbyname(hostname)

# Έλεγχος αν η IP είναι μέσα στα επιτρεπόμενα υποδίκτυα
def check_ip(config):
    current_ip = get_current_ip()
    ip_in_allowed_subnet = any(
        ipaddress.IPv4Address(current_ip) in ipaddress.IPv4Network(subnet)
        for subnet in config["ALLOWED_SUBNETS"]
    )
    if not ip_in_allowed_subnet:
        print(f"Η IP {current_ip} δεν ανήκει σε επιτρεπόμενα υποδίκτυα. Τερματισμός.")
        exit()

# Έλεγχος αν ο χρήστης είναι εξουσιοδοτημένος
def check_user(config):
    current_user = os.getlogin()
    if current_user not in config["ALLOWED_USERS"]:
        print(f"Ο χρήστης {current_user} δεν έχει δικαίωμα εκτέλεσης του script. Τερματισμός.")
        exit()

# Έλεγχος αν το script εκτελείται ως διαχειριστής
def check_admin():
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        is_admin = False
    if not is_admin:
        print("Το script απαιτεί διαχειριστικά δικαιώματα. Τερματισμός.")
        exit()

# Αλλαγή ονόματος και εγγραφή στο domain
def rename_and_join(new_name, config):
    try:
        # Αλλαγή ονόματος υπολογιστή
        subprocess.run(["powershell", "-Command", f"Rename-Computer -NewName {new_name} -Force -Restart"], check=True)
        # Εγγραφή στο domain
        subprocess.run([
            "powershell", "-Command",
            f"Add-Computer -DomainName 'localdomain.local' -Credential (New-Object System.Management.Automation.PSCredential ('{config['AD_USERNAME']}', (ConvertTo-SecureString '{config['AD_PASSWORD']}' -AsPlainText -Force))) -Force -Restart"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Σφάλμα κατά την αλλαγή ονόματος ή το join στο domain: {e}")

# Κυρίως πρόγραμμα
def main():
    # Δημιουργία ή επεξεργασία ρυθμίσεων αν ζητηθεί
    if len(sys.argv) > 1 and sys.argv[1] == "/newconf":
        create_or_edit_config()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "/genkey":
        generate_key()
        return
    # Φόρτωση ρυθμίσεων
    config = load_config()

    # Έλεγχοι ασφαλείας
    check_admin()  # Έλεγχος διαχειριστικών δικαιωμάτων
    check_user(config)  # Έλεγχος εξουσιοδοτημένου χρήστη
    check_ip(config)  # Έλεγχος τοποθεσίας (IP Range ή Subnet)

    # Δημιουργία νέου ονόματος υπολογιστή
    current_ip = get_current_ip()
    if current_ip.startswith("172.18.100."):
        prefix = "IT-"
    elif current_ip.startswith("172.18.108."):
        prefix = "BR8-"
    else:
        print("Η IP δεν ανήκει σε γνωστό υποδίκτυο. Τερματισμός.")
        return

    # Υπολογισμός νέου ονόματος
    new_name = f"{prefix}{len(config['ALLOWED_USERS']) + 1:03d}"  # Δημιουργία ονόματος
    print(f"Το νέο όνομα υπολογιστή: {new_name}")

    # Αλλαγή ονόματος και join στο domain
    rename_and_join(new_name, config)

if __name__ == "__main__":
    main()
