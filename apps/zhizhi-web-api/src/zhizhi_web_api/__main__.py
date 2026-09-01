"""Run the Zhizhi Web API process."""

from gewu_core.http.runner import run_http_service


def main() -> None:
    run_http_service(
        "zhizhi_web_api.app:app",
        "Run the Zhizhi Web API service.",
    )


if __name__ == "__main__":
    main()
