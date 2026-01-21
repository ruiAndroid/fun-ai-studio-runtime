import gzip
import logging
import os
import shutil
from datetime import datetime, timedelta
from logging import Handler, LogRecord
from pathlib import Path
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


class SizeAndTimeGzipRotatingFileHandler(Handler):
    """
    写入 app.log，并按天 + 按大小分片滚动压缩到 app.YYYY-MM-DD.i.log.gz
    """

    def __init__(
        self,
        log_dir: str,
        max_bytes: int = 100 * 1024 * 1024,
        max_history_days: int = 30,
        total_size_cap_bytes: int = 5 * 1024 * 1024 * 1024,
        clean_on_start: bool = True,
        encoding: str = "utf-8",
    ):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.active_path = self.log_dir / "app.log"
        self.max_bytes = max(1, int(max_bytes))
        self.max_history_days = max(1, int(max_history_days))
        self.total_size_cap_bytes = max(0, int(total_size_cap_bytes))
        self.clean_on_start = bool(clean_on_start)
        self.encoding = encoding

        self._stream = open(self.active_path, "a", encoding=self.encoding, buffering=1)
        self._day = datetime.now().strftime("%Y-%m-%d")
        if self.clean_on_start:
            self._cleanup()

    def emit(self, record: LogRecord) -> None:
        try:
            msg = self.format(record)
            self._maybe_rotate()
            self._stream.write(msg + "\n")
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream:
                self._stream.close()
        finally:
            super().close()

    def _maybe_rotate(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            size = self.active_path.stat().st_size if self.active_path.exists() else 0
        except Exception:
            size = 0
        if today != self._day or size >= self.max_bytes:
            self._rotate(self._day)
            self._day = today

    def _rotate(self, day: str) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass
        try:
            self._stream.close()
        except Exception:
            pass

        if self.active_path.exists() and self.active_path.stat().st_size > 0:
            i = self._next_index(day)
            plain = self.log_dir / f"app.{day}.{i}.log"
            gz = self.log_dir / f"app.{day}.{i}.log.gz"
            try:
                os.replace(self.active_path, plain)
                with open(plain, "rb") as f_in, gzip.open(gz, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                plain.unlink(missing_ok=True)
            except Exception:
                pass

        self._stream = open(self.active_path, "a", encoding=self.encoding, buffering=1)
        self._cleanup()

    def _next_index(self, day: str) -> int:
        prefix = f"app.{day}."
        max_i = -1
        for p in self.log_dir.glob(prefix + "*.log.gz"):
            name = p.name
            try:
                mid = name[len(prefix) :]
                i_str = mid.split(".")[0]
                max_i = max(max_i, int(i_str))
            except Exception:
                continue
        return max_i + 1

    def _cleanup(self) -> None:
        cutoff = datetime.now() - timedelta(days=self.max_history_days)
        for p in self.log_dir.glob("app.*.*.log.gz"):
            try:
                parts = p.name.split(".")
                day = parts[1]
                dt = datetime.strptime(day, "%Y-%m-%d")
                if dt < cutoff:
                    p.unlink()
            except Exception:
                continue

        if self.total_size_cap_bytes <= 0:
            return
        files = []
        total = 0
        for p in self.log_dir.glob("app.*.*.log.gz"):
            try:
                st = p.stat()
                files.append((st.st_mtime, p, st.st_size))
                total += st.st_size
            except Exception:
                continue
        if total <= self.total_size_cap_bytes:
            return
        files.sort(key=lambda x: x[0])
        for _, p, sz in files:
            if total <= self.total_size_cap_bytes:
                break
            try:
                p.unlink()
                total -= sz
            except Exception:
                continue


def setup_logging(service_name: str = "fun-ai-studio-runtime") -> None:
    """
    Runtime-Agent 日志落盘：
    - 默认目录：/data/funai/logs/fun-ai-studio/fun-ai-studio-runtime
    - 环境变量覆盖：FUNAI_LOG_DIR
    """
    log_dir = _env("FUNAI_LOG_DIR", f"/data/funai/logs/fun-ai-studio/{service_name}")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    max_bytes = int(_env("FUNAI_LOG_MAX_FILE_SIZE_BYTES", str(100 * 1024 * 1024)))
    max_history = int(_env("FUNAI_LOG_MAX_HISTORY_DAYS", "30"))
    total_cap = int(_env("FUNAI_LOG_TOTAL_SIZE_CAP_BYTES", str(5 * 1024 * 1024 * 1024)))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if getattr(root, "_funai_file_logging_configured", False):
        return

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = SizeAndTimeGzipRotatingFileHandler(
        log_dir=log_dir,
        max_bytes=max_bytes,
        max_history_days=max_history,
        total_size_cap_bytes=total_cap,
        clean_on_start=True,
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    setattr(root, "_funai_file_logging_configured", True)
    logging.getLogger(__name__).info("logging configured: dir=%s", log_dir)


