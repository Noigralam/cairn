"""Read/write shadows.toml — shadow profile configuration."""
import os
import tomllib
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHADOWS_PATH = os.path.join(_REPO_ROOT, "shadows.toml")


def load() -> dict:
    """Load shadows.toml. Returns {} if file does not exist."""
    try:
        with open(SHADOWS_PATH, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise RuntimeError(f"Failed to parse shadows.toml: {e}") from e


def _fmt(val) -> str:
    """Serialize a value to TOML inline string."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        s = f"{val:.10g}"
        if "." not in s and "e" not in s and "E" not in s:
            s += ".0"
        return s
    if isinstance(val, list):
        parts = ", ".join(f'"{v}"' if isinstance(v, str) else _fmt(v) for v in val)
        return f"[{parts}]"
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(val)


def save(data: dict) -> None:
    """Write data back to shadows.toml atomically."""
    lines = []
    for section in ("spot", "futures"):
        sec = data.get(section)
        if not sec:
            continue
        lines.append(f"[{section}]\n")
        if "profiles" in sec:
            lines.append(f"profiles = {_fmt(sec['profiles'])}\n")
        lines.append("\n")
        for name, overrides in sec.items():
            if name == "profiles" or not isinstance(overrides, dict):
                continue
            lines.append(f"[{section}.{name}]\n")
            for k, v in overrides.items():
                lines.append(f"{k} = {_fmt(v)}\n")
            lines.append("\n")

    dir_ = os.path.dirname(SHADOWS_PATH)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".toml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(lines)
        os.replace(tmp, SHADOWS_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
