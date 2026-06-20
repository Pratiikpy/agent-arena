"""Vercel serverless entry — exposes the Agent Arena FastAPI app.

The signed firewall, /verify, /pubkey, /leaderboard (from committed evidence), /debate, and
the UI are stateless and run here. The live arena (/live) is stateful and is not persisted on
serverless — use a container host (DEPLOY.md / render.yaml) for the continuously-running arena.
Certificates are self-verifying (each embeds its own public key + signature), so verification
works even though serverless cold starts may use a fresh signing key.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # so the app's relative evidence/ and web/ paths resolve

from bitarena.api.app import create_app  # noqa: E402

app = create_app()
