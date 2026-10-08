from gewu_core.http.runner import run_http_service


def main() -> None:
    run_http_service("zhizhi_portal_api.app:create_app", "Run the test-only Zhizhi Portal")
