"""Give an existing account the admin role (for recovery when no admin can sign in).

Usage:  py scripts/make_admin.py <username>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import auth  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
name = auth.normalise_username(sys.argv[1])
users = auth._load()
if name not in users:
    sys.exit(f"No account called {name!r}. Existing: {', '.join(sorted(users)) or 'none'}")
users[name]["role"] = "admin"
auth._save(users)
auth.audit("command line", "make admin", name)
print(f"{name} is now an administrator.")
