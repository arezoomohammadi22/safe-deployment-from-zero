"""Static checks with only Python stdlib. Does NOT replace actual NGINX/kubectl tests."""
from pathlib import Path
import re
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]


class CanaryConfigTests(unittest.TestCase):
    def test_profiles_have_expected_upstream_weights(self) -> None:
        for name, (v1, v2) in {
            "95-5": (95, 5), "80-20": (80, 20), "100-0": (100, 0), "0-100": (0, 100)
        }.items():
            with self.subTest(name=name):
                text = (ROOT / "nginx" / f"{name}.conf").read_text(encoding="utf-8")
                for version, weight in [(1, v1), (2, v2)]:
                    config_value = "down" if weight == 0 else f"weight={weight}"
                    self.assertIn(f"server app-v{version}:8000 {config_value};", text)
                self.assertIn("proxy_pass http://checkout_backend;", text)
                self.assertIn("listen 8080;", text)
                self.assertEqual(len(re.findall(r"^upstream checkout_backend", text, re.MULTILINE)), 1)

    def test_gateway_route_profiles_exist(self) -> None:
        for profile in ("95-5", "80-20", "100-0", "0-100"):
            text = (ROOT / "kubernetes" / f"httproute-{profile}.yaml").read_text()
            self.assertIn("apiVersion: gateway.networking.k8s.io/v1", text)
            self.assertIn("kind: HTTPRoute", text)
            self.assertIn("name: checkout-v1", text)
            self.assertIn("name: checkout-v2", text)

    def test_docker_compose_never_exposes_apps_directly(self) -> None:
        text = (ROOT / "compose.yml").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:", text)
        self.assertIn("APP_VERSION: v1", text)
        self.assertIn("APP_VERSION: v2", text)
        self.assertIn("./nginx/active.conf:/etc/nginx/conf.d/default.conf:ro", text)


if __name__ == "__main__":
    result = unittest.main(verbosity=2)
