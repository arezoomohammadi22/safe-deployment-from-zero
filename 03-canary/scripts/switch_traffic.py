"""Select an NGINX traffic profile without replacing bind-mounted file inode.

Usage: python3 scripts/switch_traffic.py 80-20
Then validate and reload nginx as explained in README.
"""
from pathlib import Path
import argparse

PROFILES = ("95-5", "80-20", "100-0", "0-100")


def select(profile: str, nginx_dir: Path) -> Path:
    if profile not in PROFILES:
        raise ValueError(f"Invalid profile: {profile}")
    source = nginx_dir / f"{profile}.conf"
    target = nginx_dir / "active.conf"
    # Write IN PLACE: replacing via rename/replace can leave an old Docker bind mount inode.
    with target.open("w", encoding="utf-8") as fp:
        fp.write(source.read_text(encoding="utf-8"))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose canary traffic distribution")
    parser.add_argument("profile", choices=PROFILES)
    args = parser.parse_args()
    nginx_dir = Path(__file__).resolve().parents[1] / "nginx"
    path = select(args.profile, nginx_dir)
    print(f"Profile {args.profile} written to {path}")
    print("NEXT: docker compose -f compose.yml exec -T nginx nginx -t")
    print("THEN: docker compose -f compose.yml exec -T nginx nginx -s reload")


if __name__ == "__main__":
    main()
