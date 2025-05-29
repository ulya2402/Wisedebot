from cryptography.fernet import Fernet, InvalidToken

class CryptoUtil:
    def __init__(self, encryption_key: str):
        if not encryption_key:
            raise ValueError("Encryption key cannot be empty.")
        try:
            self.fernet = Fernet(encryption_key.encode())
        except Exception as e:
            # Ini bisa terjadi jika kuncinya tidak valid format base64 Fernet
            raise ValueError(f"Invalid encryption key format: {e}")

    def encrypt_data(self, data: str) -> str | None:
        if not data:
            return None
        try:
            return self.fernet.encrypt(data.encode()).decode()
        except Exception as e:
            print(f"Encryption failed: {e}")
            return None

    def decrypt_data(self, encrypted_data: str) -> str | None:
        if not encrypted_data:
            return None
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except InvalidToken: # Error spesifik jika token/data terenkripsi tidak valid
            print("Decryption failed: Invalid token or malformed encrypted data.")
            return None
        except Exception as e:
            print(f"Decryption failed with an unexpected error: {e}")
            return None
