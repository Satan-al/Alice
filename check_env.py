import os
import sys

def log(msg):
    print(f"[env_check] {msg}", file=sys.stderr)

def check_env():
    ok = True

    # Проверка переменных окружения
    for var in ("TG_API_ID", "TG_API_HASH", "TG_SESSION"):
        if not os.getenv(var):
            log(f"❌ ENV variable {var} is not set")
            ok = False
        else:
            log(f"✅ {var} is set")

    # Проверка импорта pyrogram
    try:
        import pyrogram
        log("✅ pyrogram is installed")
    except ImportError:
        log("❌ pyrogram is NOT installed")
        ok = False

    # Проверка tgcrypto
    try:
        from pyrogram import crypto
        log("✅ tgcrypto (crypto backend) is available")
    except Exception as e:
        log(f"❌ tgcrypto is not working: {e}")
        ok = False

    if ok:
        log("🎉 Environment looks OK")
    else:
        log("⚠️ Environment check FAILED")

if __name__ == "__main__":
    check_env()
