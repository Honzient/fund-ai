"""桌面版启动入口（原生客户端窗口，非浏览器）。

架构：
- 后端 FastAPI 在进程内线程运行，仅绑定 127.0.0.1（不对外暴露）；
- 界面通过 WebView2（Windows 10/11 内置 Edge 内核）渲染在独立原生窗口中：
  自己的标题栏/任务栏图标，无地址栏、无浏览器依赖、无命令行窗口；
- 数据/存储/日志写入 %LOCALAPPDATA%/FundAI，无需管理员权限；
- 关闭窗口即退出。若 WebView2 缺失则回退浏览器模式并提示。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

APP_NAME = "基金智能分析预测平台"
DEFAULT_PORT = 8000


def _app_data_dir() -> Path:
    base = os.environ.get("FUNDAI_HOME")
    if base:
        return Path(base)
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "FundAI"
    return Path.home() / ".fundai"


def _resource_path(rel: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / rel
    return Path(__file__).resolve().parents[2] / rel


def find_free_port(start: int = DEFAULT_PORT) -> int:
    import socket

    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("未找到可用端口")


def _show_error(title: str, message: str) -> None:
    """窗口化模式下无控制台，用系统对话框提示错误。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    data_dir = _app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # 窗口化 EXE 无控制台：先把标准输出重定向到日志文件，避免 print/日志写入报错
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    except Exception:  # noqa: BLE001
        pass

    # 必须在导入 app 之前设置环境变量（配置在导入时读取）
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(data_dir / 'fund.db').as_posix()}")
    os.environ.setdefault("STORAGE_DIR", str(data_dir / "storage"))
    os.environ.setdefault("LOG_DIR", str(data_dir / "logs"))
    os.environ.setdefault("SEED_DEMO_DATA", "true")
    os.environ.setdefault("DATA_PROVIDER_ORDER", "eastmoney,mock")
    os.environ.setdefault("MODEL_JOBS", "1")
    os.environ.setdefault("FUNDAI_FRONTEND_DIR", str(_resource_path("frontend_dist")))

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    try:
        import uvicorn  # noqa: PLC0415

        from app.main import create_app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _show_error("FundAI 启动失败", f"服务初始化失败：{exc}\n详见日志目录：{data_dir / 'logs'}")
        raise

    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="fundai-server")
    server_thread.start()
    time.sleep(1.5)

    if os.environ.get("FUNDAI_OPEN_BROWSER") == "1":
        _fallback_browser_mode(url, server, server_thread)
        return

    # ---------------- 原生客户端窗口（WebView2） ----------------
    try:
        import webview  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _show_error(
            "FundAI 启动失败",
            f"客户端窗口组件加载失败：{exc}\n\n将回退为浏览器模式（可手工访问 {url}）。",
        )
        _fallback_browser_mode(url, server, server_thread)
        return

    window_closed = threading.Event()

    def on_closed() -> None:
        window_closed.set()

    try:
        window = webview.create_window(
            APP_NAME,
            url,
            width=1440,
            height=900,
            min_size=(1024, 700),
            background_color="#0b0e14",
            confirm_close=False,
            text_select=True,
        )
        window.events.closed += on_closed
        # 阻塞主线程：窗口关闭后返回
        webview.start(debug=False, private_mode=False)
    except Exception as exc:  # noqa: BLE001
        _show_error(
            "FundAI 客户端窗口启动失败",
            f"WebView2 初始化失败：{exc}\n\n请安装 Microsoft Edge WebView2 运行库后重试，"
            f"或临时访问 {url} 使用浏览器模式。",
        )
        _fallback_browser_mode(url, server, server_thread)
        return
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


def _fallback_browser_mode(url: str, server, server_thread: threading.Thread) -> None:
    """WebView2 不可用时的降级：打开浏览器并等待退出信号。"""
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    _show_error(
        "FundAI（浏览器模式）",
        f"已为您打开浏览器访问 {url}\n\n本窗口关闭后服务将停止。",
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
