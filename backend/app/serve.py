import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000, workers=1, access_log=False)


if __name__ == "__main__":
    main()
