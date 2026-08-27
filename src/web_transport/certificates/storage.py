# -*- coding: utf-8 -*-
"""证书存储：目录布局、原子写入与私钥文件权限。

布局（DATA_DIR 为数据目录）：

    DATA_DIR/certs/
    ├─ self-signed/
    │  ├─ server.crt
    │  ├─ server.key
    │  └─ fingerprint.txt
    └─ locks/            # 预留：多实例续期互斥（阶段 C）

镜像与安装包不得内置任何共享私钥；本模块只操作运行期数据目录。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.web_transport.certificates.base import CertificateError


class CertificateStore:
    def __init__(self, data_dir: Path) -> None:
        self.certs_dir = data_dir / "certs"
        self.self_signed_dir = self.certs_dir / "self-signed"
        self.locks_dir = self.certs_dir / "locks"

    # ---- 路径 ----

    @property
    def self_signed_cert_path(self) -> Path:
        return self.self_signed_dir / "server.crt"

    @property
    def self_signed_key_path(self) -> Path:
        return self.self_signed_dir / "server.key"

    @property
    def self_signed_fingerprint_path(self) -> Path:
        return self.self_signed_dir / "fingerprint.txt"

    def ensure_layout(self) -> None:
        for directory in (self.self_signed_dir, self.locks_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise CertificateError(f"无法创建证书目录 {directory}：{exc}") from exc

    # ---- 写入 ----

    def atomic_write_bytes(self, path: Path, payload: bytes, private: bool = False) -> None:
        """临时文件 + 原子替换写入。private=True 时收紧私钥文件权限。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if private:
                    _restrict_private_file(tmp_path)
                tmp_path.replace(path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
        except OSError as exc:
            raise CertificateError(f"写入 {path.name} 失败：{exc}") from exc


def _restrict_private_file(path: Path) -> None:
    """私钥权限：POSIX owner-only；Windows 无法可靠 chmod，依赖用户目录 ACL。"""
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError:
            # 权限收紧失败不阻断写入：数据目录本身应已具备访问边界。
            pass
