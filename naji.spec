# PyInstaller spec para Naji Desktop
# Build: python -m PyInstaller naji.spec --noconfirm --clean

import re
import sys
from pathlib import Path


def _version_tuple():
    init = Path(SPECPATH) / "naji" / "__init__.py"
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)', init.read_text(encoding="utf-8"))
    parts = match.group(1).split(".") if match else ["0", "0", "0"]
    while len(parts) < 4:
        parts.append("0")
    return tuple(int(p) for p in parts[:4])


_version = _version_tuple()
_version_str = ".".join(str(p) for p in _version)

version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_version,
            prodvers=_version,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Naji"),
                            StringStruct("FileDescription", "Naji Desktop"),
                            StringStruct("FileVersion", _version_str),
                            StringStruct("InternalName", "naji"),
                            StringStruct("OriginalFilename", "naji.exe"),
                            StringStruct("ProductName", "Naji"),
                            StringStruct("ProductVersion", _version_str),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

a = Analysis(
    ['naji/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
hiddenimports=[
        'sounddevice',
        'numpy',
        'pydantic',
        'pydantic_settings',
        'yaml',
        'httpx',
        'websockets',
        'ddgs',
        'openwakeword',
        'openwakeword.model',
        'openwakeword.utils',
        'openwakeword.vad',
        'onnxruntime',
        'scipy',
        'sklearn',
        'sklearn.linear_model',
        'sklearn.pipeline',
        'sklearn.preprocessing',
        'tqdm',
        'requests',
        'naji.core.tools.datetime',
        'naji.core.tools.media_control',
        'naji.core.tools.notification',
        'naji.core.tools.screenshot',
        'naji.core.tools.timer',
        'naji.core.tools.volume_control',
        'naji.core.tools.weather',
        'naji.core.tools.web_search',
        'naji.core.tools.app_control',
        'naji.core.tools.file_control',
        'naji.core.tools.power',
        'naji.core.tools.window_control',
        'qasync',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'jupyter',
        'notebook',
        'IPython',
        'pytest',
        'ruff',
        'sphinx',
        'docutils',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtWebChannel',
        'PySide6.QtWebChannelQuick',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtPdfWidgetsQuick',
        'PySide6.QtQml',
        'PySide6.QtQmlCore',
        'PySide6.QtQmlModels',
        'PySide6.QtQmlXmlListModel',
        'PySide6.QtQmlWorkerScript',
        'PySide6.QtQmlMeta',
        'PySide6.QtQmlNetwork',
        'PySide6.QtQmlLocalStorage',
        'PySide6.QtQuick',
        'PySide6.QtQuick3D',
        'PySide6.QtQuick3DAnimation',
        'PySide6.QtQuick3DAssetImport',
        'PySide6.QtQuick3DAssetUtils',
        'PySide6.QtQuick3DEffects',
        'PySide6.QtQuick3DExtras',
        'PySide6.QtQuick3DHelpers',
        'PySide6.QtQuick3DHelpersImpl',
        'PySide6.QtQuick3DIblBaker',
        'PySide6.QtQuick3DParticles',
        'PySide6.QtQuick3DPhysics',
        'PySide6.QtQuick3DPhysicsHelpers',
        'PySide6.QtQuick3DRuntimeRender',
        'PySide6.QtQuick3DSpatialAudio',
        'PySide6.QtQuick3DUtils',
        'PySide6.QtQuick3DXr',
        'PySide6.QtQuickControls2',
        'PySide6.QtQuickDialogs2',
        'PySide6.QtQuickEffects',
        'PySide6.QtQuickLayouts',
        'PySide6.QtQuickShapes',
        'PySide6.QtQuickTemplates2',
        'PySide6.QtQuickTimeline',
        'PySide6.QtQuickVectorImage',
        'PySide6.QtQuickWidgets',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSpatialAudio',
        'PySide6.QtTest',
        'PySide6.QtTextToSpeech',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtSensors',
        'PySide6.QtSerialBus',
        'PySide6.QtSerialPort',
        'PySide6.QtWebSockets',
        'PySide6.QtWebView',
        'PySide6.QtHelp',
        'PySide6.QtDesigner',
        'PySide6.QtUiTools',
        'PySide6.QtSql',
        'PySide6.QtXml',
        'PySide6.QtConcurrent',
        'PySide6.QtNetworkAuth',
        'PySide6.QtHttpServer',
        'PySide6.QtLabsAnimation',
        'PySide6.QtLabsFolderListModel',
        'PySide6.QtLabsPlatform',
        'PySide6.QtLabsQmlModels',
        'PySide6.QtLabsSettings',
        'PySide6.QtLabsSharedImage',
        'PySide6.QtLabsStyleKit',
        'PySide6.QtLabsSynchronizer',
        'PySide6.QtLabsWavefrontMesh',
        'PySide6.QtGraphs',
        'PySide6.QtGraphsWidgets',
        'PySide6.QtLottie',
        'PySide6.QtLottieVectorImage',
        'PySide6.QtCanvasPainter',
        'PySide6.QtShaderTools',
        'PySide6.QtStateMachine',
        'PySide6.QtVirtualKeyboard',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPrintSupport',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

# Filtros para reduzir tamanho
a.datas = [d for d in a.datas if not any(x in d[0] for x in ['__pycache__', '.pyc', '.git'])]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='naji',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if sys.platform == 'win32' else 'assets/icon.png',
    version=version_info,
)

