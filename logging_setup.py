import logging
from typing import Optional


class ServiceFilter(logging.Filter):
    """A logging filter that adds service and environment information to log records.

    Attributes:
        service_name: The name of the service.
        env: The environment in which the service is running.
    """
    def __init__(self, service_name: str, env: str):
        super().__init__()
        self.service_name = service_name
        self.env = env

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        """Adds service and environment information to a log record.

        Args:
            record: The log record to filter.

        Returns:
            True.
        """
        record.service = self.service_name
        record.env = self.env
        return True


def configure_logging(service_name: str, env: Optional[str] = None, level: int = logging.INFO) -> None:
    """Configures structured, human-readable logging with common labels.

    Args:
        service_name: The name of the service.
        env: The environment in which the service is running.
        level: The logging level.
    """

    env_name = env or "prod"

    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.addFilter(ServiceFilter(service_name, env_name))
        root_logger.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(service)s] [env=%(env)s] %(name)s: %(message)s",
    )
    logging.getLogger().addFilter(ServiceFilter(service_name, env_name))
