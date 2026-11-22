"""Make the secret settings for the built-in administrator account.

Usage:  py scripts/hash_password.py <admin-username> ["Display Name"]
You will be asked for the password (it is not shown or saved). Paste the printed
lines into .streamlit/secrets.toml (local) or the app's Secrets (Streamlit Cloud).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import USERNAME_RE, hash_for_secret, normalise_username, password_problems  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
user = normalise_username(sys.argv[1])
if not USERNAME_RE.match(user):
    sys.exit("Username must be 3-32 characters: lowercase letters, numbers, dot, dash or underscore.")
pw = getpass.getpass("Admin password: ")
if pw != getpass.getpass("Repeat password: "):
    sys.exit("Passwords don't match.")
problems = password_problems(pw, user)
if problems:
    sys.exit("Password needs " + ", ".join(problems) + ".")
print(f'COURSEPATH_ADMIN_USERNAME = "{user}"')
print(f'COURSEPATH_ADMIN_PASSWORD_HASH = "{hash_for_secret(pw)}"')
if len(sys.argv) > 2:
    print(f'COURSEPATH_ADMIN_DISPLAY_NAME = "{sys.argv[2]}"')
