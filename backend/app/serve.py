import logging

import uvicorn

from app.observability import SafeJsonFormatter


def main() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("dbo.operations").info('{"event":"startup","provider_diagnostics":true}')
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000, workers=1, access_log=False)


if __name__ == "__main__":
    main()
