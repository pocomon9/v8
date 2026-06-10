"""
Poco-Prime-Omega Credentials
 - In GitHub Actions: GH_PAT is injected via secrets (job-level env)
 - Fallback: XOR-decoded from embedded encoded strings (for local runs if env not set)
"""
import os as _os

def _dk(s, k=b'PocoPrimeOmega2026'):
    b = bytes.fromhex(s)
    return ''.join(chr(c ^ k[i % len(k)]) for i, c in enumerate(b))

# These are the XOR-encoded fallback tokens (used ONLY if env var not present)
# env var takes priority — set GH_PAT in GitHub Secrets or locally
_GT_ENC  = "290c0c1d06322d190c11105c542557657d7e6217552e47401745213c1c785831123e6b6453617c5c12360b07112b383f0e3e54542d654066513e080a44072a462e5d3d180e240e307e6a05621a302b303d172a2235513e25171f0e5a5a"
_GTF_ENC = "290c0c1d06322d190c11105c542557657d7e6217552e47401745213c1c785831123e6b6453617c5c12360b07112b383f0e3e54542d654066513e080a44072a462e5d3d180e240e307e6a05621a302b303d172a2235513e25171f0e5a5a"

class Accounts:
    GITHUB_USERNAME   = "pocomon9"
    GITHUB_PASSWORD   = "NEXUSPRIME--1112"
    GITHUB_FIRST_REPO = "https://github.com/pocomon9/v1"

    @classmethod
    def github_token(cls):
        """
        Priority: $GH_PAT env var (set via GitHub Secret) > XOR fallback.
        GitHub Actions injects GH_PAT via job-level env from secrets.GH_PAT.
        """
        from_env = _os.environ.get("GH_PAT", "").strip()
        if from_env and from_env.startswith("github_pat_"):
            return from_env
        if from_env and from_env.startswith("ghp_"):
            return from_env
        # Fallback: decode from embedded encoded string (local dev)
        try:
            return _dk(_GT_ENC)
        except Exception:
            return from_env  # Return whatever env has (even empty)

    @classmethod
    def github_token_fg(cls):
        """Fine-grained PAT — same priority logic."""
        from_env = _os.environ.get("GH_PAT_FG", _os.environ.get("GH_PAT", "")).strip()
        if from_env and (from_env.startswith("github_pat_") or from_env.startswith("ghp_")):
            return from_env
        try:
            return _dk(_GTF_ENC)
        except Exception:
            return from_env

    TWITTER_USERNAME    = "pocomon9"
    TWITTER_PASSWORD    = "NEXUSPRIME--1112"
    TWITTER_DM_PASSCODE = "2000"
    GOOGLE_EMAIL    = "dprjfacts@gmail.com"
    GOOGLE_PASSWORD = "D4P16R18J10"
    PROTON_USERNAME = "nexusprime1112@proton.me"
    PROTON_PASSWORD = "NEXUSPRIME--1112k"
    CHROME_PROFILE_PATH = 'cook'
    BRO_REPO     = 'https://github.com/pocomon9/bro.git'
    BRO_REPO_NAME = 'bro'
    CHATGPT_URL   = 'https://chatgpt.com'
    DEEPSEEK_URL  = 'https://chat.deepseek.com'
    CHATGPT_EMAIL    = "dprjfacts@gmail.com"
    CHATGPT_PASSWORD = "D4P16R18J10k"
    DEEPSEEK_EMAIL   = "dprjfacts@gmail.com"
    DEEPSEEK_PASSWORD = "D4P16R18J10"
    OTP_ROUTING = {
        "github":  ["gmail", "protonmail"],
        "twitter": ["gmail"],
        "x.com":   ["gmail"],
        "default": ["gmail", "protonmail"],
    }
    NEW_ACCOUNTS = []
