# -*- coding: utf-8 -*-
"""
工具箱启动器（代号 ToolBox）
整合 自研工具 根目录下全部工具，可视化分组面板统一调取。

核心能力：
  1. Alt+Space 全局热键唤起/隐藏面板（Win32 RegisterHotKey 原生方案，
     规避 keyboard 库 Win+L 锁屏后热键失效的已知坑）
  2. 工具自动发现：解析 TOOLS.md 登记表 + 扫描根目录兜底，新工具自动进「未分组」
  3. 分组拖拽 + 持久化（data/config.json），以工具目录名为主键（与 TOOLS.md 对齐）
  4. 单实例互斥：重复启动弹窗提示退出，热键不冲突
  5. 失焦自动隐藏：JS window.blur 事件 → hide_panel()
"""
import base64
import ctypes
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import webview

# WebView2 白屏根治（2026-08-29）：Chromium 原生窗口遮挡检测会把屏外(-32000)窗口判为
# hidden 并挂起光栅化；长时间挂起后移回屏内偶发合成器恢复失败 → 整窗纯白（JS 仍活着）。
# 禁用该特性让屏外窗口不再被挂起（须在 webview.start 创建浏览器进程前设置）。
os.environ.setdefault('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS',
                      '--disable-features=CalculateNativeWinOcclusion')

# ---------- 路径定位（兼容 PyInstaller onefile：配置与页面随 exe 所在目录） ----------
APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
ROOT = APP_DIR.parent                      # 自研工具根目录
TOOLS_MD = ROOT / 'TOOLS.md'
CONFIG_PATH = APP_DIR / 'data' / 'config.json'
WEB_PAGE = APP_DIR / 'web' / 'index.html'
ICONS_DIR = APP_DIR / 'data' / 'icons'     # 自定义应用图标缓存（从 exe 提取的 PNG）
REPORTS_DIR = APP_DIR / 'data' / 'reports'  # 工作日报 md 副本（data/reports/YYYY-MM-DD.md，人工查看/外部流转）
DB_PATH = APP_DIR / 'data' / 'reports.db'   # 日报权威存储（SQLite，年度述职数据源；含按日量化快照列）
USAGE_PATH = APP_DIR / 'data' / 'usage.json'  # AI token 用量记账（累计 + 按日，花费按记录时点单价折算）
ASSETS_DIR = REPORTS_DIR / 'assets'        # 微信截屏素材库（assets/YYYY-MM-DD/HHMMSS.png）
SELF_DIR_NAME = APP_DIR.name               # 扫描时排除自身

# ---------- Win32 常量与句柄 ----------
MOD_ALT = 0x0001
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_CLOSE = 0x0010
ERROR_ALREADY_EXISTS = 183
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SW_RESTORE = 0x09                        # 恢复最小化窗口
WM_SYSCOMMAND = 0x0112
SC_RESTORE = 0xF120
SM_CXSCREEN, SM_CYSCREEN = 0, 1
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

OFFSCREEN = -32000   # "隐藏"= 移出屏幕（绕开 ShowWindow 显示语义：pywebview WinForms 层
                     # 在 WM_SHOWWINDOW 处理链上会使跨线程 ShowWindow 延迟数秒生效）
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080   # 工具窗口：不占任务栏、不进 Alt+Tab（唤起全靠热键）

# 64 位下句柄参数显式声明，避免 ctypes 默认 32 位截断
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
# 侧键截屏确认框（MB_YESNO 等）；64 位下返回值显式声明
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_uint]
user32.MessageBoxW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_longlong
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
user32.SetWindowLongPtrW.restype = ctypes.c_longlong
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = ctypes.c_bool
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND   # 64 位 HWND 不声明 restype 会被截断
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = ctypes.c_bool
user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.c_bool]
user32.AttachThreadInput.restype = ctypes.c_bool
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = ctypes.c_bool
user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, ctypes.c_uint]
user32.RedrawWindow.restype = ctypes.c_bool
# 鼠标 LL 钩子三件套：64 位下不声明 restype 会把 HHOOK/HMODULE 句柄截断成 32 位
# （实锤：GetModuleHandleW(None) 截断 → SetWindowsHookExW 报 126 ERROR_MOD_NOT_FOUND）
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, wintypes.HANDLE, wintypes.HMODULE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = ctypes.c_bool
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, ctypes.c_size_t, ctypes.c_size_t]
user32.CallNextHookEx.restype = ctypes.c_longlong
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def find_hwnd(title='YY工具箱'):
    """按窗口标题枚举顶层窗口句柄（ShowWindow 需句柄而非 pywebview 窗口对象）。"""
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(h, buf, 64)
        if buf.value == title:
            found.append(h)
            return False
        return True
    found = []
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


# ============================== 工具发现 ==============================

def parse_tools_md() -> dict:
    """解析 TOOLS.md 登记表 → {目录名: {name,port,type,desc,date}}；文件缺失/格式异常返回空表。"""
    result = {}
    try:
        lines = TOOLS_MD.read_text(encoding='utf-8').splitlines()
    except OSError:
        return result
    for line in lines:
        if not line.lstrip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 6:
            continue
        # 跳过表头行与 |---|---| 分隔行
        if cells[0] == '工具名' or set(cells[0]) <= {'-', ' ', ':'}:
            continue
        name, port, _tech, desc, date, dirname = cells[:6]
        dirname = dirname.rstrip('\\').strip()
        if not dirname:
            continue
        # 类型判定：端口列含数字→Web；标注「脚本」→bat；标注「桌面」→桌面
        if any(ch.isdigit() for ch in port):
            ptype = 'web'
        elif '脚本' in port:
            ptype = 'bat'
        else:
            ptype = 'desk'
        result[dirname] = {'name': name, 'port': port, 'type': ptype, 'desc': desc, 'date': date}
    return result


def find_target(tool_dir: Path):
    r"""探测工具启动入口，优先级：release 内 exe（onefile/onedir）> 启动.bat > app.py > 目录内其他 bat。
    release 优先（2026-08-31 用户要求：集成挂打包 exe，不依赖 .venv/streamlit 调试环境，
    且规避 winnat 保留端口段这类环境坑；2026-09-02 起发布产物自 dist/ 迁移至 release/）；
    注意源码迭代后需重新发布才会反映到面板启动。
    最后一级兜底纯 bat 脚本类（主脚本名自定义，如 killport.bat，非模板名 启动.bat）。
    返回 (kind, path)：kind ∈ {'file', 'py', None}。"""
    release = tool_dir / 'release'
    if release.is_dir():
        exes = sorted(release.glob('*.exe'))        # onefile：release\xxx.exe
        if exes:
            return 'file', exes[0]
        for sub in sorted(release.iterdir()):       # onedir：release\{名}\{名}.exe
            if sub.is_dir() and (sub / f'{sub.name}.exe').is_file():
                return 'file', sub / f'{sub.name}.exe'
    bat = tool_dir / '启动.bat'
    if bat.is_file():
        return 'file', bat
    app = tool_dir / 'app.py'
    if app.is_file():
        return 'py', app
    others = sorted(p for p in tool_dir.glob('*.bat') if p.name != '启动.bat')
    if others:
        return 'file', others[0]                    # 多个 bat 时取排序第一个（纯 bat 类目录通常仅一个主脚本）
    return None, None


def scan_tools() -> list:
    """合并 TOOLS.md 元数据与根目录扫描，返回工具列表（TOOLS.md 漏登的目录也兜底纳入）。"""
    meta = parse_tools_md()
    tools = []
    for child in sorted(ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith('.') or child.name == SELF_DIR_NAME:
            continue
        kind, target = find_target(child)
        if kind is None:
            continue
        m = meta.get(child.name) or {}
        tools.append({
            'dir': child.name,
            'name': m.get('name') or child.name,
            'type': m.get('type') or ('bat' if (kind == 'file' and target.suffix == '.bat') else 'desk'),
            'desc': m.get('desc', ''),
            'port': m.get('port', ''),
            'kind': kind,
            'target': str(target),
        })
    return tools


def scan_external(cfg: dict) -> list:
    """扫描外部工具目录（config.json 的 external_dirs）下的裸 exe/bat。
    主键用 ext:{文件名} 前缀，与根目录扫描的目录名主键隔离防撞。"""
    tools = []
    for d in cfg.get('external_dirs', []):
        p = Path(d)
        if not p.is_dir():
            continue
        files = sorted(p.glob('*.exe')) + sorted(p.glob('*.bat'))
        for f in files:
            tools.append({
                'dir': f'ext:{f.stem}',
                'name': f.stem,
                'type': 'bat' if f.suffix == '.bat' else 'desk',
                'desc': '',
                'port': '',
                'kind': 'file',
                'target': str(f),
            })
    return tools


def all_tools(cfg: dict) -> list:
    """全量工具 = 根目录扫描 + 外部目录扫描 + 自定义应用（launch 与 get_all 共用）。"""
    return scan_tools() + scan_external(cfg) + scan_apps(cfg)


def scan_bgs() -> list:
    """背景图目录 web/bg 下的图片文件名列表（换图=放新图进去；多张时前端随机取一张）。"""
    d = APP_DIR / 'web' / 'bg'
    if not d.is_dir():
        return []
    exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    return sorted(f.name for f in d.iterdir() if f.suffix.lower() in exts)


def clean_path(s: str) -> str:
    """清洗路径：资源管理器「复制文件地址」会带 U+202A~U+202E 方向控制符（不可见），
    粘贴进文件对话框后混入路径 → Path.is_file() 恒 False（用户实报"添加 exe 失败"）。"""
    return ''.join(ch for ch in s if ord(ch) not in (0x200E, 0x200F) and not (0x202A <= ord(ch) <= 0x202E)).strip().strip('"')


def app_id_of(path) -> str:
    """exe 全路径 → 稳定 id（小写路径 md5 前 10 位）：同一路径重复添加天然去重。
    兼容 str / Path 入参（曾因 Path 无 .lower() 使 UI 添加流程全挂，无头验证传 str 未覆盖）。"""
    return 'a' + hashlib.md5(str(path).lower().encode('utf-8')).hexdigest()[:10]


def extract_icon(exe: Path, app_id: str):
    """从 exe 提取内嵌图标 → data/icons/{id}.png（ExtractIconEx + Pillow 转 BGRA）。
    有缓存直接返回；提取失败（无图标 exe）返回 None，前端回落 🧩 默认图标。"""
    out = ICONS_DIR / f'{app_id}.png'
    if out.is_file():
        return f'../data/icons/{out.name}'
    try:
        import win32gui, win32ui
        from PIL import Image
        large = win32gui.ExtractIconEx(str(exe), 0)[0]
        if not large:
            return None
        hicon = large[0]
        size = 32
        hdc0 = win32gui.GetDC(0)                 # 屏幕原始 DC（用完 ReleaseDC）
        hdc = win32ui.CreateDCFromHandle(hdc0)   # 只读包装，不拥有句柄 → 不可 DeleteDC
        memdc = hdc.CreateCompatibleDC()         # 自建内存 DC（用完 DeleteDC）
        bmp = win32ui.CreateBitmap()             # 自建位图（用完 DeleteObject）
        try:
            bmp.CreateCompatibleBitmap(hdc, size, size)
            old = memdc.SelectObject(bmp)
            try:
                win32gui.DrawIconEx(memdc.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, 3)  # DI_NORMAL
                info = bmp.GetInfo()
                bits = bmp.GetBitmapBits(True)
                img = Image.frombuffer('RGBA', (info['bmWidth'], info['bmHeight']),
                                       bits, 'raw', 'BGRA', 0, 1)
                ICONS_DIR.mkdir(parents=True, exist_ok=True)
                img.save(out)
            finally:
                memdc.SelectObject(old)
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            memdc.DeleteDC()
            win32gui.ReleaseDC(0, hdc0)
            win32gui.DestroyIcon(hicon)
        return f'../data/icons/{out.name}'
    except Exception:
        return None


APP_EXTS = {'.exe', '.html', '.htm'}   # 可添加为本地应用的扩展名（html 走默认浏览器）


def scan_apps(cfg: dict) -> list:
    """自定义本地应用（config.apps：手动添加的 exe/html/目录），过滤已失效路径；图标惰性提取。
    html 无内嵌图标 → 前端按 web 类型回落地球 SVG；目录 → dir 类型文件夹卡（资源管理器打开）。"""
    tools = []
    for a in cfg.get('apps', []):
        p = Path(a.get('path', ''))
        if p.is_dir():                                   # 目录卡：资源管理器打开
            typ, icon = 'dir', None
        elif p.suffix.lower() in APP_EXTS and p.is_file():
            typ = 'web' if p.suffix.lower() in ('.html', '.htm') else 'app'
            icon = extract_icon(p, a['id']) if p.suffix.lower() == '.exe' else None
        else:
            continue
        tools.append({
            'dir': f"app:{a['id']}",
            'name': a.get('name') or p.stem,
            'type': typ,
            'desc': str(p),
            'port': '',
            'kind': 'file',
            'target': str(p),
            'icon': icon,
        })
    return tools


# ============================== 分组配置 ==============================

def load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
            if isinstance(cfg.get('groups'), list) and isinstance(cfg.get('ungrouped'), list):
                cfg.setdefault('external_dirs', [])   # 外部工具目录（裸 exe/bat），可手工追加
                cfg.setdefault('todos', [])           # 待办事项 [{id, text, created_at}]
                cfg.setdefault('todo_history', [])    # 闭环历史（前端维护，最近 20 条）
                cfg.setdefault('active_group', None)  # 上次打开的分组（ Ungrouped 用 __ungrouped__）
                cfg.setdefault('active_widget', None)  # 右下角上次使用的小工具（pomo/notes…）
                cfg.setdefault('notes_pages', [''])    # 记事本多页内容（HTML 数组）
                cfg.setdefault('notes_page', 0)        # 记事本当前页索引
                cfg.setdefault('pomo_focus', 25)       # 番茄钟专注时长（分钟）
                cfg.setdefault('pomo_rest', 5)         # 番茄钟休息时长（分钟）
                cfg.setdefault('bg_enabled', True)    # 背景图开关（图放 web/bg/，多张随机）
                cfg.setdefault('apps', [])            # 手动添加的本地应用 [{id,name,path}]
                cfg.setdefault('report_repos', [])     # 日报 git 仓库路径列表（本地扫描，无需 gitee 令牌）
                cfg.setdefault('report_author', '')    # 提交作者过滤（空=自动取 git 全局 user.email）
                cfg.setdefault('report_wechat_name', '')  # 本人微信昵称（聊天记录逐条带发送者名，AI 靠它区分谁在说话）
                cfg.setdefault('wechat_shot', True)   # 鼠标侧键截屏素材：按侧键截前台窗口存当日素材库
                cfg.setdefault('shot_crop_left', 335)  # 截屏裁掉左侧像素（微信左栏+列表栏≈300，0=整窗）
                cfg.setdefault('report_export_dir', '')  # 日报一键另存目录（如 D:\company\机器狗\工作日报）
                cfg.setdefault('ai_api', {})           # 云端 AI（OpenAI 兼容）：{base_url, api_key, model}
                return cfg
        except (OSError, ValueError):
            pass  # 配置损坏则回退默认，不阻断启动
    return {'groups': [], 'ungrouped': [], 'external_dirs': [], 'todos': [],
            'todo_history': [], 'active_group': None, 'bg_enabled': True, 'apps': []}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def reconcile(cfg: dict, tools: list) -> dict:
    """配置与实际工具集对账：新工具→未分组；已删工具→各组与未分组中清出。"""
    dirs = {t['dir'] for t in tools}
    for g in cfg['groups']:
        g['tools'] = [d for d in g['tools'] if d in dirs]
    cfg['groups'] = [g for g in cfg['groups'] if isinstance(g, dict) and g.get('name')]
    known = {d for g in cfg['groups'] for d in g['tools']} | set(cfg['ungrouped'])
    for t in tools:
        if t['dir'] not in known:
            cfg['ungrouped'].append(t['dir'])
    cfg['ungrouped'] = [d for d in cfg['ungrouped'] if d in dirs]
    return cfg


# ============================== 工作日报 ==============================
# 数据来源（2026-09-03 定版）：① 本地 git 仓库扫描（git log --author 过滤，无需 gitee 令牌/网络）；
# ② 微信聊天摘录（微信 4.x 本地库加密，自动读取需读进程内存提取密钥，成本高且随版本失效——
#    故走前端粘贴框）；③ AI 对话摘要（同粘贴）。三素材 → 云端 AI（OpenAI 兼容）生成草稿 →
#    前端编辑定稿 → 按 data/reports/YYYY-MM-DD.md 归档（日历徽标数据源）。

DAY_RE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')


def valid_day(day: str) -> bool:
    """日期串白名单校验：报表文件名由 day 直接拼接，必须先过格式关。"""
    return bool(DAY_RE.fullmatch(day or ''))


def git_author_default() -> str:
    """作者过滤默认值 = git 全局 user.email（本机 yangyang@yunda.com）；取不到则不过滤。"""
    try:
        r = subprocess.run(['git', 'config', '--global', 'user.email'],
                           capture_output=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return r.stdout.decode('utf-8', 'ignore').strip()
    except Exception:
        return ''


def scan_repo_commits(repo: str, day: str, author: str) -> dict:
    """扫单个 git 仓库某天的提交。author 含 % 通配由 git 自己解释（--author 模式匹配）。
    每条提交附带改动统计（--shortstat）与涉及模块（--name-only 目录归并）、提交说明（%b）——
    一行标题喂给 AI 只能得到照抄式日报（用户实报"统计过于简单"），丰富素材才能聚类扩写。
    输出用 \\x1e（记录分隔）+ @@STAT@@（body/stat 分界）切分，规避 body 多行破坏逐行解析。
    返回 {'repo': 末级目录名, 'commits': [{'h','s','t','body','stat','dirs'}], 'err': None|原因}——
    err 不抛异常：某仓库失效不应拖垮整次扫描（前端逐仓显示错误行）。"""
    name = Path(repo.rstrip('\\/')).name or repo
    if not Path(repo).is_dir():
        return {'repo': name, 'commits': [], 'err': '目录不存在'}
    cmd = ['git', '-C', repo, 'log',
           f'--since={day} 00:00:00', f'--until={day} 23:59:59',
           '-m', '--first-parent',   # merge 提交默认无 diff 输出（用户仓库实锤：当日提交是 merge）
           '--pretty=format:%x1e%h%x1f%s%x1f%ad%x1f%b%x1f@@STAT@@',
           '--numstat', '--date=format:%H:%M']   # numstat 而非 shortstat+name-only：git 的 diff
    # 输出格式单选，两者同给只剩一个；numstat 一份输出同时含增删行数与文件路径（自行汇总）
    if author:
        cmd.append(f'--author={author}')
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {'repo': name, 'commits': [], 'err': 'git 命令超时（15s）'}
    if r.returncode != 0:
        err = r.stderr.decode('gbk', 'ignore').strip().splitlines()
        return {'repo': name, 'commits': [], 'err': (err[0][:80] if err else 'git 执行失败')}
    out = r.stdout.decode('utf-8', 'ignore')
    # %x1f（单元分隔符）分列：subject 里可能带 | 等字符，| 作分隔会切错列
    commits = []
    for part in out.split('\x1e'):
        if not part.strip():
            continue
        pre, _, post = part.partition('@@STAT@@')
        try:
            h, s, t, body = pre.split('\x1f', 3)
        except ValueError:
            continue                    # 结构不完整（如空 body 边界），跳过该条
        s = s.strip()
        if not s:
            continue
        files_n = ins = dels = 0
        dirs = set()
        for ln in post.splitlines():
            bits = ln.strip().split('\t')
            if len(bits) < 3:
                continue
            files_n += 1
            if bits[0] != '-':          # '-' = 二进制文件，无行数
                try:
                    ins += int(bits[0])
                    dels += int(bits[1])
                except ValueError:
                    pass
            pp = Path(bits[2].replace('\\', '/')).parts   # 路径前两段≈模块/子模块（Java 深包全路径太长）
            if pp:
                dirs.add('/'.join(pp[:2]) if len(pp) > 1 else pp[0])
        stat = f"{files_n}文件 +{ins}/-{dels}" if files_n else ''
        body = ' '.join(body.split())[:300]   # 多行 body 压单行，限长防素材爆炸
        commits.append({'h': h, 's': s, 't': t, 'body': body,
                        'stat': stat, 'dirs': sorted(dirs)[:4],
                        'files': files_n, 'ins': ins, 'dels': dels})   # 数值字段供今日统计直加
    return {'repo': name, 'commits': commits, 'err': None}


# 日报体例（2026-09-07 用户定版）：四节结构，不要明日计划；全文 ≤150 字、目标 80 字左右
# （用户实锤"日常生成过长了"）；开发内容与影响范围为王，严禁代码行数/文件数统计入正文
REPORT_BODY_HINT = ("### 今日完成\n"
                    "- 按项目/工作主题分组，每节至多 1-2 条、每条一句话：写清开发内容与影响范围"
                    "（做了什么、解决什么问题、涉及哪些模块），标注已完成/进行中\n\n"
                    "### 微信工作沟通要点\n"
                    "- （来自微信素材的沟通、需求与协作要点；素材无微信内容则省略本节）\n\n"
                    "### 其他事项\n"
                    "- （领导临时安排、会议、面试/接待等零散工作；无则省略本节）\n\n"
                    "### 问题与风险\n"
                    "- （当前遇到的问题、阻塞项与风险；无则省略本节）")


def build_report_prompt(day: str, commit_lines: str, wechat: str, ai_summary: str,
                        wechat_name: str = '') -> str:
    """AI 日报草稿 prompt：体例四节（今日完成/微信沟通要点/其他事项/问题与风险），
    不要明日计划、严禁代码量统计入正文（2026-09-04 用户定版）；
    全文 ≤150 字目标 80 字左右（2026-09-07 用户定版）。
    严禁编造素材外内容（日报要能对外交差，真实性优先）。
    表述要求主题聚类+研发视角扩写（素材已含改动规模/模块/提交说明）——
    照抄提交标题式日报被用户实报"统计过于简单"。
    wechat_name=本人微信昵称：聊天记录逐条带发送者名，AI 靠它区分本人发言与他人
    向本人提出的需求/任务（用户实锤格式：名称\\nYYYY年MM月DD日 HH:MM\\n内容）。"""
    wx_rule = (f'- 微信素材需按发言者区分：本人（{wechat_name}）的发言反映自己的工作安排与沟通；'
               '其他人的发言中向本人提出的需求、任务、问题与协作请求，是今日工作内容的重要来源；'
               '〔截图素材〕OCR 文本来自聊天窗口截图，含时间碎片与界面杂讯，取其有实际语义的对话内容即可\n'
               if wechat_name else
               '- 〔截图素材〕OCR 文本来自聊天窗口截图，含时间碎片与界面杂讯，'
               '取其有实际语义的对话内容即可；未配置本人微信昵称，无法可靠区分发言者身份\n')
    return (f'请根据下方素材，为「杨阳」撰写 {day} 的工作日报草稿。\n'
            '要求：\n'
            '- 只依据素材撰写，严禁编造素材中不存在的工作内容；语言简洁、专业\n'
            '- 长度硬约束：正文总字数不超过 150 字，尽量 80 字左右；每节至多 1-2 条、每条一句话，'
            '短句直述，删掉一切修饰、铺垫与重复信息\n'
            '- 「今日完成」按工作主题聚类：同主题的多次提交合并为一条，用研发视角表述'
            '（做了什么、解决什么问题、影响哪些模块），体现工作含量；'
            '严禁逐条罗列提交标题或照抄提交原文——提交明细是素材，不是格式；'
            '严禁把「+N/-M 行」「N 个文件」等代码量统计写进正文（改动统计仅供你判断工作量）\n'
            f'{wx_rule}'
            '- 用 Markdown 按以下四节结构输出（无内容的节省略；不要明日计划、不要一级标题、不要人名标题）：\n'
            f'{REPORT_BODY_HINT}\n\n'
            f'## 素材一：git 提交明细（{day}，括号内为涉及模块）\n{commit_lines or "（无提交记录）"}\n\n'
            f'## 素材二：微信素材（聊天摘录粘贴 + 截图 OCR 识别文本，〔〕标记为单张截图）\n{wechat or "（无）"}\n\n'
            f'## 素材三：其他工作事项补充（领导临时安排、面试/接待、与 AI 协作摘要等零散工作）\n{ai_summary or "（无）"}\n')


def ai_endpoint(base_url: str) -> str:
    """OpenAI 兼容端点补全。规则（HTTP 404 实锤教训：智谱 /v4 曾被强插成 /v4/v1/...）：
    带 URL 路径段的（/v4、/v1、/compatible-mode/v1 等）直接拼 /chat/completions；
    只有裸域名才补默认版本段 /v1。已给全端点的原样使用。"""
    u = (base_url or '').strip().rstrip('/')
    if u.endswith('/chat/completions'):
        return u
    from urllib.parse import urlparse
    if urlparse(u).path:                      # 有路径段（非裸域名）
        return u + '/chat/completions'
    return u + '/v1/chat/completions'


def ai_chat_stream(base_url: str, api_key: str, model: str, prompt: str, on_delta,
                   images=None, timeout: int = 60):
    """流式 chat/completions（SSE）。on_delta(reasoning, content) 逐段回调——
    思考过程取 delta.reasoning_content（智谱 GLM / DeepSeek 思考模型字段，无则空串）。
    images = base64 png 列表（微信截屏素材）：走 OpenAI 兼容视觉消息（image_url data URI），
    要求所选模型支持视觉（如 glm-5.3-flash），不支持时厂商会报 4xx 透传前端。
    外部调用三要素：连接/单次读 60s 超时；不做自动重试（流式断点续传无意义，
    已收部分由任务槽保留、错误透传前端）；api_key 只进请求头不入日志。"""
    import urllib.request
    user_content = prompt
    if images:
        user_content = [{'type': 'text', 'text': prompt}] + [
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b}'}} for b in images]
    body = json.dumps({'model': model, 'temperature': 0.3, 'stream': True,
                       'stream_options': {'include_usage': True},   # OpenAI 兼容：流式末尾带 usage（记账用）；智谱等忽略未知字段
                       'messages': [
        {'role': 'system', 'content': '你是软件研发团队的工作日报助手，只输出 Markdown 正文。'},
        {'role': 'user', 'content': user_content},
    ]}).encode('utf-8')
    req = urllib.request.Request(
        ai_endpoint(base_url), data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}',
                 'Accept': 'text/event-stream'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        usage = None
        for raw in resp:
            line = raw.decode('utf-8', 'ignore').strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if payload == '[DONE]':
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue            # 非 JSON 心跳/注释行，跳过
            if obj.get('usage'):
                usage = obj['usage']   # 流式 usage 在末尾若干 chunk（OpenAI 兼容含 stream_options 时）
            delta = (obj.get('choices') or [{}])[0].get('delta', {})
            on_delta(delta.get('reasoning_content') or '', delta.get('content') or '')
        return usage


# AI 生成任务槽（单任务即可：日报一次只有一个生成在跑；跨线程读写全走锁）
_AI_TASK = {'id': None, 'status': 'idle', 'reasoning': '', 'content': '', 'why': ''}
_AI_TASK_LOCK = threading.Lock()
# 截屏后台 OCR 任务槽（单槽，seq 单调递增；前端步骤②轮询 seq 变化刷新素材列表）
_OCR_TASK = {'seq': 0, 'status': 'idle', 'day': '', 'name': '', 'chars': 0}
_OCR_TASK_LOCK = threading.Lock()
# 侧键确认框互斥（MessageBox 挂着等用户点时忽略新侧键，防多框叠加）
_SHOT_CONFIRMING = {'on': False}
_SHOT_CONFIRM_LOCK = threading.Lock()


# ============================== 鼠标侧键截屏（微信素材采集） ==============================
# 方案定版（2026-09-03 用户拍板）：微信 4.1 解密库路线成本过高（Frida 注入+版本偏移逆向+杀软
# 对抗，见 README 可行性报告），改为鼠标侧键一键截前台窗口 → 当日素材库 → 生成日报时最近
# 5 张喂视觉模型。不吞鼠标事件（CallNextHookEx 照常传递），侧键原有功能不受影响。

WM_XBUTTONDOWN = 0x020B
WH_MOUSE_LL = 14


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('pt', wintypes.POINT), ('mouseData', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class ShotHookThread(threading.Thread):
    """WH_MOUSE_LL 低级鼠标钩子线程：XBUTTON1/2（侧键）按下 → 派发截图动作。
    LL 钩子回调经本线程消息循环派发，且回调必须快速返回（系统超时会摘钩）——
    截图（百毫秒级）丢工作线程执行。进程退出前必须 stop() 摘钩。"""

    def __init__(self, on_xbutton, logger=None):
        super().__init__(daemon=True)
        self.on_xbutton = on_xbutton
        self.logger = logger or (lambda msg: None)
        self.hook = None
        self._cb_ref = None    # 保引用防 GC（钩子回调被回收会直接崩进程）
        self._last = 0.0       # 防抖：X 键按下+双击连触发

    def _cb(self, n_code, w_param, l_param):
        if n_code == 0 and w_param == WM_XBUTTONDOWN:
            info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            btn = (info.mouseData >> 16) & 0xFFFF    # HIWORD：1=XBUTTON1，2=XBUTTON2
            now = time.time()
            if btn in (1, 2) and now - self._last > 0.8:
                self._last = now
                threading.Thread(target=self.on_xbutton, daemon=True).start()
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self):
        # WPARAM/LPARAM 按 UINT_PTR 语义用 c_size_t（64 位安全），不用 wintypes 的 32 位 c_uint
        cb = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, ctypes.c_size_t, ctypes.c_size_t)(self._cb)
        self._cb_ref = cb
        self.hook = user32.SetWindowsHookExW(WH_MOUSE_LL, cb, kernel32.GetModuleHandleW(None), 0)
        self.logger(f'shot hook: {"ok" if self.hook else "FAILED"}')
        if not self.hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass

    def stop(self):
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None


def shot_foreground_window(crop_left: int = 0) -> str:
    """截取前台窗口 → 当日素材库 png，返回文件名。BitBlt 屏幕 DC（前台窗口无遮挡，
    用户正在看的窗口即素材）。crop_left = 裁掉左侧像素（微信 4.1 自绘 UI 不暴露内部
    布局（UIA 实测仅 3 元素），无法自动定位聊天区——固定裁左栏+列表栏，量可配置）。
    局限（V1 已知）：截图 DC 为主屏，窗口整体在副屏时拒截。
    进程未声明 DPI aware，按系统虚拟化坐标截图，内容与像素一致。"""
    import win32gui
    import win32ui
    from PIL import Image
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError('没有前台窗口')
    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    left += max(0, int(crop_left or 0))       # 裁左侧（保护：裁后过窄则视为配置过大，回退整窗）
    cx, cy = user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)
    left, top, right, bot = max(0, left), max(0, top), min(cx, right), min(cy, bot)
    if right - left < 60 or bot - top < 60:
        raise RuntimeError('窗口不在主屏可视范围内（或裁剪配置过大）')
    hdc0 = win32gui.GetDC(0)
    hdc = win32ui.CreateDCFromHandle(hdc0)
    memdc = hdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    w, h = right - left, bot - top
    try:
        bmp.CreateCompatibleBitmap(hdc, w, h)
        memdc.SelectObject(bmp)
        win32gui.BitBlt(memdc.GetSafeHdc(), 0, 0, w, h, hdc.GetSafeHdc(), left, top, 0x00CC0020)  # SRCCOPY
        info = bmp.GetInfo()
        img = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']),
                               bmp.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
        day = time.strftime('%Y-%m-%d')
        d = ASSETS_DIR / day
        d.mkdir(parents=True, exist_ok=True)
        name = time.strftime('%H%M%S') + '.png'
        img.save(d / name)
        return name
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        memdc.DeleteDC()
        win32gui.ReleaseDC(0, hdc0)


# ---- 截屏素材本地 OCR（方案定版 2026-09-04：RapidOCR 文本化替代视觉读图，省 90% token）----
# 引擎惰性单例：首次侧键触发才 import+加载模型（~5s），常驻缓存；OCR 纯本地离线
_OCR_ENGINE = None
_OCR_LOCK = threading.RLock()   # 可重入：ocr_png 内层再锁串行化推理，_get_ocr 外层锁不冲突


def _get_ocr():
    global _OCR_ENGINE
    with _OCR_LOCK:
        if _OCR_ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
        return _OCR_ENGINE


def ocr_png(path) -> str:
    """图片 → 文本（RapidOCR）。推理全程持锁串行（连按侧键不并发跑模型）；识别失败抛异常由调用方降级。"""
    with _OCR_LOCK:
        eng = _get_ocr()
        result, _ = eng(str(path))
    return '\n'.join(line[1] for line in (result or []))


def assemble_wechat_material(wechat: str, ocr_blocks: list) -> str:
    """素材二组装 = 用户粘贴摘录 + 截图 OCR 识别文本（每张一段，带时间戳标签）。"""
    parts = []
    if wechat and wechat.strip():
        parts.append(wechat.strip())
    parts.extend(f"〔截图素材 {label} 识别文本〕\n{body}" for label, body in ocr_blocks)
    return '\n\n'.join(parts)


# ---- 日报 SQLite 权威存储（2026-09-04：年度述职数据源；md 文件保留为人工查看/外部流转副本）----
# sqlite3 标准库零依赖，与纯离线原则一致。量化快照列（提交/行数/番茄/待办/token）在保存日报时落库，
# 年度述职可直接 SELECT 聚合出全年报表；首次使用自动把 data/reports/*.md 旧档迁移入库（幂等）。
_DB_READY = {'path': None}


def _report_summary(text: str) -> str:
    """日报摘要 = 正文第一个非标题非空行（口径与 report_recent 旧逻辑一致，供列表预览）。
    加粗 ** 一并剥掉（迁移实锤：旧日报条目为 - **标题**：…，列表预览曾裸露星号）。"""
    for l in (text or '').splitlines():
        l = l.strip()
        if not l or l.startswith('#'):
            continue
        cand = l.lstrip('#-*> ').replace('**', '').strip()
        if cand:
            return cand[:42]
    return ''


def _db():
    """打开日报库连接并确保表结构存在。连接按调用新建（本工具写入频率极低，无需长连接池）；
    路径在调用时读模块属性（无头测试 monkeypatch DB_PATH 后自动落到临时目录并重建表）。"""
    path = Path(DB_PATH)
    if _DB_READY['path'] != str(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(path))
        con.execute('''CREATE TABLE IF NOT EXISTS reports(
            day TEXT PRIMARY KEY, content TEXT NOT NULL, summary TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            commits INTEGER DEFAULT 0, ins INTEGER DEFAULT 0, dels INTEGER DEFAULT 0,
            repos INTEGER DEFAULT 0,
            pomo_min INTEGER DEFAULT 0, pomo_sessions INTEGER DEFAULT 0,
            todo_created INTEGER DEFAULT 0, todo_closed INTEGER DEFAULT 0,
            tokens_p INTEGER DEFAULT 0, tokens_c INTEGER DEFAULT 0, ai_cost REAL DEFAULT 0,
            assets_cnt INTEGER DEFAULT 0,
            exported INTEGER DEFAULT 0, export_path TEXT DEFAULT '')''')
        # 旧 md 档迁移：库中缺哪天补哪天（重装/删库后重开不丢历史）
        known = {r[0] for r in con.execute('SELECT day FROM reports')}
        reports_dir = Path(REPORTS_DIR)
        if reports_dir.is_dir():
            for f in sorted(reports_dir.glob('*.md')):
                if not valid_day(f.stem) or f.stem in known:
                    continue
                try:
                    text = f.read_text(encoding='utf-8')
                    con.execute('INSERT OR IGNORE INTO reports(day, content, summary, updated_at) '
                                'VALUES(?,?,?,?)',
                                (f.stem, text, _report_summary(text),
                                 time.strftime('%Y-%m-%d %H:%M', time.localtime(f.stat().st_mtime))))
                except (OSError, sqlite3.Error):
                    continue
        con.commit()
        _DB_READY['path'] = str(path)
        return con
    return sqlite3.connect(str(path))


# ============================== 全局热键 ==============================

class HotkeyThread(threading.Thread):
    """独立线程注册 Alt+Space 并泵消息；规避 keyboard 库锁屏失效坑。"""

    def __init__(self, on_toggle, logger=None):
        super().__init__(daemon=True)
        self.on_toggle = on_toggle
        self.logger = logger or (lambda msg: None)
        self.tid = None
        self.ok = False

    def run(self):
        self.tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, MOD_ALT, VK_SPACE):
            self.logger('hotkey: 注册失败（Alt+Space 被占用）')
            user32.MessageBoxW(
                None, '注册全局热键 Alt+Space 失败：可能被其他软件占用。\n面板仍可用，但热键唤起不可用。',
                'YY工具箱', 0x10)
            return
        self.ok = True
        self.logger('hotkey: 注册成功')
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:   # WM_QUIT 或错误
                break
            if msg.message == WM_HOTKEY and msg.wParam == 1:
                try:
                    self.on_toggle()
                except Exception:
                    pass
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)


# ============================== 前端桥接 API ==============================

class Api:
    """前端桥接 API。
    ⚠ 铁律：实例上严禁挂 pywebview 对象引用（Window/HotkeyThread 等）——pywebview 初始化
    js bridge 时会深扫描 Api 属性，挂上 Window 会拖进 .NET 代理递归（Rectangle.op_Equality
    错误链）并炸死桥初始化。跨对象引用一律走模块级全局（_G_WINDOW / _G_HOTKEY）。"""

    def __init__(self):
        self.hwnd = None        # Win32 窗口句柄（int，窗口创建后回填——安全类型）
        self.visible = False    # 面板可见状态（热键 toggle 与 JS 失焦隐藏共用此标记）
        self.prev_foreground = None
        self.pick_lock = False  # 系统文件对话框期间锁定失焦隐藏（对话框弹出必然失焦，不锁则面板被藏、后续命名框弹在屏外）
        self.shown_at = 0.0     # 本次显示时刻（唤起宽限期判据）
        self.regrabbed = False  # 本次显示周期内是否已重抢过前台（防与焦点抢占型页面 ping-pong）
        self.quit_lock = False  # 退出流程标志：closing 拦截器据此放行（否则 destroy 被 Cancel 进程不退）

    # ---- 窗口显示/隐藏：移屏方案（窗口恒可见，仅移动位置）----
    def _restore_if_iconic(self):
        """最小化自愈：Win+D / Win+M / 「显示桌面」会把 TOOLWINDOW 一并最小化，
        且 SetWindowPos 对最小化窗口无效（位置被系统钉在 -32000）——不恢复则
        Alt+Space 永远「唤起无反应」。ShowWindow(SW_RESTORE) 主路径，
        500ms 未生效再投递 SC_RESTORE 系统命令兜底（跨线程 ShowWindow 有延迟前科）。"""
        if not user32.IsIconic(self.hwnd):
            return
        user32.ShowWindow(self.hwnd, SW_RESTORE)
        for _ in range(10):
            if not user32.IsIconic(self.hwnd):
                return
            time.sleep(0.05)
        self._dbg('restore: ShowWindow slow, posting SC_RESTORE')
        user32.PostMessageW(self.hwnd, WM_SYSCOMMAND, SC_RESTORE, 0)
        for _ in range(10):
            if not user32.IsIconic(self.hwnd):
                return
            time.sleep(0.05)
        self._dbg('restore: FAILED, still iconic')

    def _force_foreground(self):
        """前台强抢：SetForegroundWindow 被前台锁定拒绝（用户正操作其他窗口时）——
        先合成一次 Alt 按放（系统认为本进程收到输入，授予前台权），
        再 AttachThreadInput 附着前台线程共享输入状态重试，双保险。"""
        user32.keybd_event(0x12, 0, 0, 0)          # Alt down（前台锁经典解法）
        user32.keybd_event(0x12, 0, 2, 0)          # Alt up
        fg = user32.GetForegroundWindow()
        if not fg or fg == self.hwnd:
            user32.SetForegroundWindow(self.hwnd)   # 无前台窗口，直接再试
            return
        tid_fg = user32.GetWindowThreadProcessId(fg, None)
        tid_me = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(tid_me, tid_fg, True)
        try:
            user32.BringWindowToTop(self.hwnd)
            user32.SetForegroundWindow(self.hwnd)
        finally:
            user32.AttachThreadInput(tid_me, tid_fg, False)
        self._dbg(f'force_foreground: fg was {fg}')

    def _show_win(self):
        # 记住前一前台窗口（hide 时归还焦点），再移回屏幕中央并拉到最前
        self.prev_foreground = user32.GetForegroundWindow()
        self._restore_if_iconic()          # 防线1：解除最小化（Win+D 后唤起无反应的根因）
        rect = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            w, h = 920, 620                # GetWindowRect 异常防御
        cx, cy = user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)
        x, y = (cx - w) // 2, (cy - h) // 2
        # TOPMOST→NOTOPMOST 经典配方：强制拉到 z 序顶部并取得前台激活资格。
        # 直接 SetWindowPos(HWND_TOP) 在无前台权限时只把窗口放"当前激活窗口之下"，
        # 且 SetForegroundWindow 可能被前台锁定拒绝——表现为面板藏在别的窗口后面
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE)
        user32.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)
        if not user32.SetForegroundWindow(self.hwnd):   # 防线2：前台被拒则强抢
            self._force_foreground()
        # 防线4（白屏兜底）：1px 尺寸抖动 + 全窗口强制重绘——屏外期间 WebView2 合成器
        # 若已挂起（禁 occlusion 之前的残留状态/驱动重置），强制其重新光栅化，白屏自愈
        user32.SetWindowPos(self.hwnd, 0, 0, 0, w + 1, h, SWP_NOMOVE | SWP_NOZORDER)
        user32.SetWindowPos(self.hwnd, 0, 0, 0, w, h, SWP_NOMOVE | SWP_NOZORDER)
        RDW_INVALIDATE, RDW_UPDATENOW, RDW_ALLCHILDREN, RDW_FRAME = 0x0001, 0x0100, 0x0080, 0x0400
        user32.RedrawWindow(self.hwnd, None, None,
                            RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN | RDW_FRAME)
        # 防线3：事后校验——仍最小化或仍在屏外则把状态写进日志（下次问题可诊断）
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        self._dbg(f'show chk: iconic={user32.IsIconic(self.hwnd)}, '
                  f'rect=({rect.left},{rect.top}), fg={user32.GetForegroundWindow() == self.hwnd}')

    def _hide_win(self):
        # 先把焦点还给唤起前的窗口（否则纯移屏会让焦点留在屏外，用户打字丢失）
        prev = getattr(self, 'prev_foreground', None)
        if prev and prev != self.hwnd:
            user32.SetForegroundWindow(prev)
        user32.SetWindowPos(self.hwnd, 0, OFFSCREEN, OFFSCREEN, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)

    def get_all(self):
        """页面加载/唤起刷新时调用：扫描工具 + 对账分组配置。"""
        self._dbg('bridge: get_all called')   # 桥连通性观测（页面 JS 调到此处即证桥已通）
        cfg = load_config()
        tools = all_tools(cfg)
        reconcile(cfg, tools)
        return {'tools': tools, 'config': cfg, 'bgs': scan_bgs()}

    def launch(self, dirname: str) -> bool:
        """启动指定工具（分离进程，不阻塞面板）。exe/bat 默认管理员运行（runas 弹 UAC）。"""
        for t in all_tools(load_config()):
            if t['dir'] == dirname:
                if t['kind'] == 'py':
                    self._launch_python(t['target'])
                else:
                    self._launch_elevated(t['target'])
                return True
        return False

    @staticmethod
    def _launch_elevated(target: str):
        """按目标性质分流提权（2026-09-02 用户要求：默认管理员运行）：
        - exe/bat/cmd → os.startfile(path,'runas')（ShellExecute runas 动词，每次弹 UAC 确认）
        - html/目录 → 普通打开（浏览器/资源管理器以管理员运行是安全反模式且无提权意义）
        - UAC 被用户拒绝（winerror 1223）→ 静默；其他异常 → 回落普通启动不阻断。"""
        if not target.lower().endswith(('.exe', '.bat', '.cmd')):
            os.startfile(target)
            return
        try:
            os.startfile(target, 'runas')
        except OSError as e:
            if getattr(e, 'winerror', None) == 1223:   # 用户在 UAC 点了「否」
                return
            try:
                os.startfile(target)                    # 提权失败回落普通启动
            except OSError:
                pass

    # ---- 自定义本地应用（exe） ----
    def pick_exe(self):
        """弹出系统文件对话框选一个 exe；未选/取消返回 None，已添加过返回 {'dup': True}。
        ⚠ 两个坑（5.4 实测）：
        1) 无 webview.FILE_DIALOG_OPEN 常量——dialog_type 直接传 10（OPEN_DIALOG）；
           file_types 是 tuple 格式 ('描述 (*.exe)',)，不是 '描述|模式' 竖线字符串。
        2) js_api 回调跑在独立 Python 线程（MTA），WinForms ShowDialog 必须 STA——
           直接调必抛 ThreadStateException 被 pywebview 吞掉（表现为前端"没反应"），
           须起子线程 pythoncom.CoInitialize() 显式 STA 后再调。
        create_file_dialog 走模块级全局 _G_WINDOW（Api 禁挂 pywebview 引用，见类注释）。"""
        if not _G_WINDOW:
            return None
        import pythoncom
        box = {}
        self.pick_lock = True

        def _run_sta():
            pythoncom.CoInitialize()
            try:
                box['r'] = _G_WINDOW.create_file_dialog(
                    10, allow_multiple=False,
                    file_types=('程序 (*.exe)', '网页文件 (*.html;*.htm)'))
            except Exception as e:
                box['exc'] = repr(e)
                self._dbg(f'pick_exe dialog error: {e!r}')
            finally:
                pythoncom.CoUninitialize()

        t = threading.Thread(target=_run_sta)
        t.start()
        t.join()
        self.pick_lock = False   # 对话框关闭后恢复失焦隐藏（命名/取消阶段正常语义）
        if 'exc' in box:
            return {'err': '对话框打开失败'}          # 异常：前端 toast 提示（取消则静默 None）
        if not box.get('r'):
            return None                              # 用户取消/未选
        p = clean_path(str(Path(box['r'][0])))
        if any(a['path'].lower() == p.lower() for a in load_config().get('apps', [])):
            return {'dup': True}
        return {'path': p, 'name': Path(p).stem}

    def pick_dir(self, check_dup: bool = True):
        """弹出系统目录选择对话框（FOLDER_DIALOG=20，同 pick_exe 的 STA + pick_lock 套路）。
        check_dup=False 供日报设置复用（仓库/另存目录与自定义应用是两个体系，
        命中 apps 查重会拿不到路径）。返回 {'path','name'} / None（取消）/ {'err': ...}。"""
        if not _G_WINDOW:
            return None
        import pythoncom
        box = {}
        self.pick_lock = True

        def _run_sta():
            pythoncom.CoInitialize()
            try:
                box['r'] = _G_WINDOW.create_file_dialog(20)   # 20 = FOLDER_DIALOG（IFileDialog+FOS_PICKFOLDERS）
            except Exception as e:
                box['exc'] = repr(e)
                self._dbg(f'pick_dir dialog error: {e!r}')
            finally:
                pythoncom.CoUninitialize()

        t = threading.Thread(target=_run_sta)
        t.start()
        t.join()
        self.pick_lock = False
        if 'exc' in box:
            return {'err': '目录对话框打开失败'}
        if not box.get('r'):
            return None
        p = clean_path(str(Path(box['r'][0])))
        if check_dup and any(a['path'].lower() == p.lower() for a in load_config().get('apps', [])):
            return {'dup': True}
        return {'path': p, 'name': Path(p).name or p}

    def save_app(self, path: str, name: str) -> dict:
        """确认添加：入 config.apps 并预提取图标（失败不阻断，get_all 时会再兜底）。
        支持 exe / html / htm / 目录（html 卡片走 Web 类型默认浏览器；目录卡资源管理器打开）。
        返回 {'ok': True} / {'ok': False, 'why': 原因}（前端据 why 给准确提示）。"""
        try:
            p = Path(clean_path(path))
            if not p.is_dir():
                if p.suffix.lower() not in APP_EXTS:
                    return {'ok': False, 'why': '仅支持 exe / html 文件或文件夹'}
                if not p.is_file():
                    return {'ok': False, 'why': '文件不存在（路径含非法字符？）'}
            aid = app_id_of(p)
            cfg = load_config()
            if any(a['id'] == aid for a in cfg.get('apps', [])):
                return {'ok': False, 'why': '该应用已在列表中'}
            # 外部目录扫描已提供同文件入口（ext: 卡）时允许共存：用户加「应用」通常为要
            # 原版图标/自定义命名，拦截反而不合理；note 提示由前端 toast 说明
            note = ''
            for t in all_tools(cfg):
                if t['dir'] != f'app:{aid}' and t.get('target', '').lower() == str(p).lower():
                    note = '该文件已有外部扫描入口，本次添加为原版图标应用卡'
                    break
            cfg.setdefault('apps', []).append({'id': aid, 'name': name.strip() or p.stem, 'path': str(p)})
            save_config(cfg)
            extract_icon(p, aid)
            return {'ok': True, 'note': note}
        except Exception:
            return {'ok': False, 'why': '未知错误'}

    def remove_app(self, dirname: str) -> bool:
        """移除自定义应用（dirname = app:{id}）：出 apps、清分组归属、删图标缓存。"""
        try:
            if not dirname.startswith('app:'):
                return False
            aid = dirname[4:]
            cfg = load_config()
            cfg['apps'] = [a for a in cfg.get('apps', []) if a['id'] != aid]
            for g in cfg['groups']:
                g['tools'] = [d for d in g['tools'] if d != dirname]
            cfg['ungrouped'] = [d for d in cfg['ungrouped'] if d != dirname]
            save_config(cfg)
            icon = ICONS_DIR / f'{aid}.png'
            if icon.is_file():
                icon.unlink()
            return True
        except Exception:
            return False

    @staticmethod
    def _launch_python(app_py: str):
        """无 bat/exe 的兜底：优先用该工具自身 .venv 的 pythonw 无窗启动。"""
        d = Path(app_py).parent
        pyw = d / '.venv' / 'Scripts' / 'pythonw.exe'
        exe = str(pyw) if pyw.is_file() else sys.executable
        subprocess.Popen([exe, app_py], cwd=str(d),
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)

    def save_config(self, cfg_json: str) -> bool:
        """前端拖拽/建组/改名后即时持久化。"""
        try:
            cfg = json.loads(cfg_json)
            if not (isinstance(cfg.get('groups'), list) and isinstance(cfg.get('ungrouped'), list)):
                return False
            save_config(cfg)
            return True
        except Exception:
            return False

    # ---- 工作日报（分步向导：git 扫描 → 微信摘录 → AI 摘要 → AI 草稿 → 编辑归档）----
    # 均为纯 IO/子进程/网络操作，不碰 WinForms 对象（js_api 回调线程 MTA，文件对话框才需 STA）

    def report_get_settings(self) -> dict:
        cfg = load_config()
        return {'repos': cfg.get('report_repos', []), 'author': cfg.get('report_author', ''),
                'wechat_name': cfg.get('report_wechat_name', ''),
                'shot': bool(cfg.get('wechat_shot', True)),
                'crop_left': cfg.get('shot_crop_left', 335),
                'export_dir': cfg.get('report_export_dir', ''), 'ai': cfg.get('ai_api', {})}

    def report_save_settings(self, cfg_json: str) -> dict:
        """日报设置：仓库列表（逐行路径，过 clean_path 防方向符）/ 作者过滤 / 本人微信昵称 /
        侧键截屏开关 / 另存目录 / AI 三件套+单价。"""
        try:
            d = json.loads(cfg_json)
            cfg = load_config()
            # str(Path(p)) 归一化：正/反斜杠混输（D:/x 与 D:\x）视为同一路径去重
            repos = [str(Path(clean_path(str(r)))) for r in d.get('repos', []) if clean_path(str(r))]
            cfg['report_repos'] = sorted(set(repos))
            cfg['report_author'] = str(d.get('author', '')).strip()
            cfg['report_wechat_name'] = str(d.get('wechat_name', '')).strip()
            cfg['wechat_shot'] = bool(d.get('shot', True))
            crop = int(d.get('crop_left') or 0)
            cfg['shot_crop_left'] = max(0, min(crop, 800))   # 防负数/离谱大值
            cfg['report_export_dir'] = clean_path(str(d.get('export_dir', '')))
            ai = d.get('ai') or {}
            cfg['ai_api'] = {'base_url': str(ai.get('base_url', '')).strip().rstrip('/'),
                             'api_key': str(ai.get('api_key', '')).strip(),
                             'model': str(ai.get('model', '')).strip(),
                             'price_in': float(ai.get('price_in') or 0),    # 元/百万tokens（空=只记token不算钱）
                             'price_out': float(ai.get('price_out') or 0)}
            save_config(cfg)
            return {'ok': True}
        except (ValueError, OSError) as e:
            return {'ok': False, 'why': f'设置保存失败：{e}'}

    def report_scan_commits(self, day: str, repos_json: str = '') -> list:
        """按日扫描配置仓库的提交（repos_json 传临时列表时用于"设置未保存先试扫"）。
        作者过滤：设置指定 > git 全局 user.email > 不过滤。逐仓容错，失败仓 err 行返回。"""
        if not valid_day(day):
            return [{'repo': '?', 'commits': [], 'err': '日期格式非法（应为 YYYY-MM-DD）'}]
        cfg = load_config()
        try:
            repos = json.loads(repos_json) if repos_json else cfg.get('report_repos', [])
        except ValueError:
            repos = []
        author = cfg.get('report_author') or git_author_default()
        return [scan_repo_commits(r, day, author) for r in repos]

    def report_ai_start(self, day: str, scan_json: str, wechat: str, ai_summary: str,
                        quant_json: str = '', assets_json: str = '') -> dict:
        """异步启动 AI 生成（流式）。js_api 是"调用-返回"模型，无法把流式进度塞进
        单次返回值——故起后台线程跑流式请求，前端轮询 report_ai_poll 拉思考/正文增量。
        scan_json = report_scan_commits 结果原样回传（前端已剔除不想写进日报的提交）。
        quant_json = 前端采集的本机量化数据（番茄钟/待办），拼素材四帮 AI 体现实工作量。
        assets_json = 当日截屏素材文件名列表（兼容传 {name,...} 对象数组）。后端自读同名 .txt 的
        OCR 文本入 prompt；无 OCR 文本的图转 base64 走视觉兜底（取最近 20 张，视觉封顶 5 张防爆量）。"""
        cfg = load_config()
        ai = cfg.get('ai_api', {})
        if not (ai.get('base_url') and ai.get('api_key') and ai.get('model')):
            return {'ok': False, 'why': '未配置 AI 接口：请点⚙设置，填写接口地址 / 密钥 / 模型'}
        lines = []
        try:
            for repo in json.loads(scan_json):
                for c in repo.get('commits', []):
                    # 不拼 stat（N文件 +N/-M 行）——用户明确不要行数进日报；dirs 供 AI 判断影响范围
                    extra = ''
                    if c.get('dirs'):
                        extra += f"（涉及 {'、'.join(c['dirs'][:3])}）"
                    if c.get('body'):
                        extra += f"｜说明：{c['body']}"
                    lines.append(f"- {repo.get('repo', '')} {c.get('t', '')} {c.get('s', '')} ({c.get('h', '')}){extra}")
        except ValueError:
            return {'ok': False, 'why': '提交数据格式异常'}
        # 素材四：量化数据（git 部分后端自算，其余来自前端传参），帮 AI 在日报里体现实工作量
        quant_lines = []
        try:
            q = json.loads(quant_json) if quant_json else {}
        except ValueError:
            q = {}
        gs = self.report_today_stats(day)
        if gs.get('commits'):
            # 不报行数——行数统计被用户明确移出日报正文，素材里也不喂汇总行数
            quant_lines.append(f"- git：当日 {gs['commits']} 次提交，活跃 {gs['repos']} 个仓库")
        if q.get('pomo_min'):
            quant_lines.append(f"- 番茄钟：当日专注 {q['pomo_min']} 分钟（{q.get('pomo_sessions', '?')} 段）")
        if q.get('todo_created') or q.get('todo_closed'):
            quant_lines.append(f"- 待办：新建 {q.get('todo_created', 0)} 项、闭环 {q.get('todo_closed', 0)} 项")
        quant_block = ('\n\n## 素材四：本机工作量化数据（体现实工作量，可在草稿中自然引用，严禁夸大）\n'
                       + '\n'.join(quant_lines)) if quant_lines else ''
        # 截屏素材：优先用本地 OCR 文本（省 90% token），OCR 缺失的图降级走视觉（上限 5 张保底）
        ocr_blocks = []
        img_b64s = []
        try:
            names = json.loads(assets_json) if assets_json else []
        except ValueError:
            names = []
        for item in names[-20:]:
            # 兼容两种传参：文件名字符串 / report_wechat_assets 返回的 {name,...} 对象。
            # （根因实锤 2026-09-04：前端曾把完整对象数组原样传回，Path(str(dict)).name 不以
            #   .png 结尾被 continue 全丢——OCR 文本与视觉兜底双双进不了 prompt，日报看不到微信内容）
            name = str(item.get('name') or '') if isinstance(item, dict) else str(item)
            safe = Path(name).name
            if not (valid_day(day) and safe.endswith('.png')):
                continue
            p = ASSETS_DIR / day / safe
            if not p.is_file():
                continue
            txt_f = p.with_suffix('.txt')
            txt = ''
            try:
                if txt_f.is_file():
                    txt = txt_f.read_text(encoding='utf-8').strip()
            except OSError:
                pass
            if txt:
                ocr_blocks.append((safe[:-4], txt))
            elif len(img_b64s) < 5:      # 无 OCR 文本才走视觉，且封顶 5 张
                img_b64s.append(base64.b64encode(p.read_bytes()).decode('ascii'))
        wechat_material = assemble_wechat_material(wechat or '', ocr_blocks)
        if img_b64s:
            self._dbg(f'report ai: {len(ocr_blocks)} ocr blocks + {len(img_b64s)} vision fallback')
        prompt = build_report_prompt(day, '\n'.join(lines), wechat_material, ai_summary or '',
                                     wechat_name=cfg.get('report_wechat_name', '')) + quant_block
        tid = f't{int(time.time() * 1000)}'
        with _AI_TASK_LOCK:
            _AI_TASK.update(id=tid, status='running', reasoning='', content='', why='')

        def _run():
            try:
                def on_delta(r, c):
                    with _AI_TASK_LOCK:
                        if r:
                            _AI_TASK['reasoning'] += r
                        if c:
                            _AI_TASK['content'] += c
                usage = ai_chat_stream(ai['base_url'], ai['api_key'], ai['model'], prompt, on_delta,
                                       images=img_b64s or None)
                if usage:
                    Api._usage_add(int(usage.get('prompt_tokens', 0) or 0),
                                   int(usage.get('completion_tokens', 0) or 0),
                                   float(ai.get('price_in') or 0), float(ai.get('price_out') or 0))
                with _AI_TASK_LOCK:
                    if _AI_TASK['content'].strip():
                        _AI_TASK['status'] = 'done'
                    else:
                        _AI_TASK.update(status='error', why='AI 返回了空内容（模型可能不支持流式）')
            except Exception as e:
                self._dbg(f'report ai fail: {type(e).__name__}')   # prompt/key 均不入日志
                with _AI_TASK_LOCK:
                    _AI_TASK.update(status='error', why=f'AI 生成失败：{e}')

        threading.Thread(target=_run, daemon=True).start()
        return {'ok': True, 'task': tid}

    def report_ai_poll(self, task_id: str) -> dict:
        """前端轮询生成进度：status running/done/error + 累计的思考/正文文本。
        返回全量累计而非增量——日报文本量级小（几十 KB 上限），全量直填最简单且防乱序丢段。"""
        with _AI_TASK_LOCK:
            if task_id != _AI_TASK['id']:
                return {'status': 'gone'}     # 进程重启/被新任务覆盖
            return {'status': _AI_TASK['status'], 'reasoning': _AI_TASK['reasoning'],
                    'content': _AI_TASK['content'], 'why': _AI_TASK['why']}

    def report_get(self, day: str) -> dict:
        if not valid_day(day):
            return {'exists': False, 'text': '', 'updated': ''}
        try:
            row = _db().execute('SELECT content, updated_at FROM reports WHERE day=?', (day,)).fetchone()
            if row:
                return {'exists': True, 'text': row[0], 'updated': row[1] or ''}
        except sqlite3.Error as e:
            self._dbg(f'db get fail: {e}')
        # 库 miss 回退读 md（正常已被迁移入库，此处防手删库文件后丢档）
        p = REPORTS_DIR / f'{day}.md'
        if not p.is_file():
            return {'exists': False, 'text': '', 'updated': ''}
        try:
            return {'exists': True, 'text': p.read_text(encoding='utf-8'),
                    'updated': time.strftime('%Y-%m-%d %H:%M', time.localtime(p.stat().st_mtime))}
        except OSError as e:
            return {'exists': False, 'text': '', 'updated': '', 'err': str(e)}

    def _day_quant(self, day: str) -> dict:
        """按日量化（番茄钟/待办），口径与前端 todayQuant() 一致；保存日报时快照入库。"""
        cfg = load_config()
        pm = [x for x in cfg.get('pomo_log', []) if x.get('date') == day]
        return {'pomo_min': sum(x.get('focus_min', 0) or 0 for x in pm),
                'pomo_sessions': len(pm),
                'todo_created': sum(1 for t in cfg.get('todos', [])
                                    if (t.get('created_at') or '').startswith(day)),
                'todo_closed': sum(1 for t in cfg.get('todo_history', [])
                                   if (t.get('closed_at') or '').startswith(day))}

    def _day_usage(self, day: str) -> dict:
        """当日 AI token 记账快照（usage.json 里已有按日明细，取出入日报库供年度聚合）。"""
        try:
            data = json.loads(USAGE_PATH.read_text(encoding='utf-8'))
            d = data.get('days', {}).get(day, {})
            return {'p': int(d.get('p', 0) or 0), 'c': int(d.get('c', 0) or 0),
                    'cost': float(d.get('cost', 0) or 0)}
        except (OSError, ValueError):
            return {'p': 0, 'c': 0, 'cost': 0.0}

    def report_save(self, day: str, text: str) -> dict:
        """编辑定稿归档：权威写 SQLite（量化快照同步入库，年度述职数据源），
        同时写 data/reports/YYYY-MM-DD.md 副本（人工查看/外部流转兼容，日历等以此兜底）。"""
        if not valid_day(day):
            return {'ok': False, 'why': '日期格式非法'}
        if not (text or '').strip():
            return {'ok': False, 'why': '日报内容为空，未保存'}
        content = text.rstrip() + '\n'
        updated = time.strftime('%Y-%m-%d %H:%M')
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            p = REPORTS_DIR / f'{day}.md'
            p.write_text(content, encoding='utf-8')
            stats = self.report_today_stats(day)
            quant = self._day_quant(day)
            usage = self._day_usage(day)
            adir = ASSETS_DIR / day
            assets_cnt = len([f for f in adir.iterdir() if f.suffix == '.png']) if adir.is_dir() else 0
            con = _db()
            con.execute('INSERT OR REPLACE INTO reports(day, content, summary, updated_at, '
                        'commits, ins, dels, repos, pomo_min, pomo_sessions, todo_created, '
                        'todo_closed, tokens_p, tokens_c, ai_cost, assets_cnt) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (day, content, _report_summary(content), updated,
                         stats.get('commits', 0), stats.get('ins', 0), stats.get('dels', 0),
                         stats.get('repos', 0),
                         quant['pomo_min'], quant['pomo_sessions'],
                         quant['todo_created'], quant['todo_closed'],
                         usage['p'], usage['c'], usage['cost'], assets_cnt))
            con.commit()
            self._dbg(f'report saved: {day}')
            return {'ok': True, 'path': str(p)}
        except (OSError, sqlite3.Error) as e:
            return {'ok': False, 'why': f'写入失败：{e}'}

    def report_export(self, day: str, overwrite: bool = False) -> dict:
        """一键另存到外部日报目录（如现有 D:\\company\\机器狗\\工作日报）。
        目标已存在时不覆盖（可能是组日报），返回 exists=True 由前端确认后再带 overwrite 重调。
        成功后在库中回写导出标记（年度统计"哪些已交付"）。"""
        if not valid_day(day):
            return {'ok': False, 'why': '日期格式非法'}
        content = None
        try:
            row = _db().execute('SELECT content FROM reports WHERE day=?', (day,)).fetchone()
            if row:
                content = row[0]
        except sqlite3.Error as e:
            self._dbg(f'db export read fail: {e}')
        src = REPORTS_DIR / f'{day}.md'
        if content is None:
            if not src.is_file():
                return {'ok': False, 'why': '当日日报尚未归档，请先保存'}
            try:
                content = src.read_text(encoding='utf-8')
            except OSError as e:
                return {'ok': False, 'why': f'读取失败：{e}'}
        dest_dir = clean_path(load_config().get('report_export_dir', ''))
        if not dest_dir or not Path(dest_dir).is_dir():
            return {'ok': False, 'why': '另存目录未配置或不存在（⚙ 设置里配置）'}
        dest = Path(dest_dir) / f'{day}.md'
        if dest.is_file() and not overwrite:
            return {'ok': False, 'exists': True, 'path': str(dest), 'why': '目标文件已存在'}
        try:
            dest.write_text(content, encoding='utf-8')
            con = _db()
            con.execute('UPDATE reports SET exported=1, export_path=? WHERE day=?', (str(dest), day))
            con.commit()
            return {'ok': True, 'path': str(dest)}
        except (OSError, sqlite3.Error) as e:
            return {'ok': False, 'why': f'写入失败：{e}'}

    def report_dates(self) -> list:
        """已归档日报日期列表（日历"有日报"徽标数据源；权威来源 SQLite 库，md 枚举兜底）。"""
        try:
            return [r[0] for r in _db().execute('SELECT day FROM reports ORDER BY day')]
        except sqlite3.Error:
            if not REPORTS_DIR.is_dir():
                return []
            return sorted(f.stem for f in REPORTS_DIR.iterdir()
                          if f.is_file() and f.suffix == '.md' and valid_day(f.stem))

    def report_recent(self, n: int = 3) -> list:
        """最近 n 天日报流（widget 看板用）：[{day, summary, updated}]。
        summary/updated 保存时已落库，直接读列，不再逐文件读全文。"""
        try:
            rows = _db().execute('SELECT day, summary, updated_at FROM reports '
                                 'ORDER BY day DESC LIMIT ?', (max(1, min(int(n or 3), 10)),)).fetchall()
            return [{'day': d, 'summary': s or '', 'updated': u or ''} for d, s, u in rows]
        except (sqlite3.Error, ValueError):
            return []

    # ---- 今日工作量化统计（顶部今日条/看板/日报素材共用；git 部分带 60s 缓存防频繁扫盘）----
    _STATS_CACHE = {'key': None, 'ts': 0.0, 'data': None}

    def report_today_stats(self, day: str) -> dict:
        cfg = load_config()
        repos = cfg.get('report_repos', [])
        if not valid_day(day) or not repos:
            return {'commits': 0, 'ins': 0, 'dels': 0, 'repos': 0}
        author = cfg.get('report_author') or git_author_default()
        key = (day, tuple(repos), author)
        now = time.time()
        c = Api._STATS_CACHE
        if c['key'] == key and now - c['ts'] < 60:
            return dict(c['data'])
        n = ins = dels = nr = 0
        for repo in repos:
            r = scan_repo_commits(repo, day, author)
            for ci in r.get('commits', []):
                n += 1
                ins += ci.get('ins', 0) or 0
                dels += ci.get('dels', 0) or 0
            if r.get('commits'):
                nr += 1
        data = {'commits': n, 'ins': ins, 'dels': dels, 'repos': nr}
        c.update(key=key, ts=now, data=data)
        return dict(data)

    def report_usage(self) -> dict:
        """AI token 用量记账读取（今日 + 累计；花费按记录时点单价折算并存好）。"""
        today = time.strftime('%Y-%m-%d')
        try:
            data = json.loads(USAGE_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        d = data.get('days', {}).get(today, {})
        return {'today_p': d.get('p', 0), 'today_c': d.get('c', 0), 'today_cost': round(d.get('cost', 0), 4),
                'total_p': data.get('total_p', 0), 'total_c': data.get('total_c', 0),
                'total_cost': round(data.get('total_cost', 0), 4)}

    # ---- 鼠标侧键截屏素材库 ----
    def on_shot_xbutton(self):
        """侧键触发（钩子线程派发）：截前台窗口（按配置裁掉左侧栏）→ 原生「是/否」确认框
        （用户拍板 2026-09-07：确认后再识别，防误触截图入库）→「是」后台 OCR（完成后 toast 字数
        并推进 _OCR_TASK.seq，前端步骤②轮询刷新素材列表）；「否」删除该截图不入库。
        确认框挂着时忽略新侧键（防多框叠加）。OCR 失败图仍保留（生成时走视觉兜底）。
        开关 wechat_shot 关闭时静默忽略。"""
        png = None
        try:
            cfg = load_config()
            if not cfg.get('wechat_shot', True):
                return
            with _SHOT_CONFIRM_LOCK:
                if _SHOT_CONFIRMING['on']:
                    return
                _SHOT_CONFIRMING['on'] = True
            try:
                name = shot_foreground_window(int(cfg.get('shot_crop_left', 335) or 0))
                day = time.strftime('%Y-%m-%d')
                png = ASSETS_DIR / day / name
                # 后台/屏外进程无前台权限，直接弹窗会被前台锁定压成任务栏闪烁（用户实锤"弹窗显示不出来"）。
                # 双保险：AttachThreadInput 借当前前台线程的输入队列获得弹窗权限（配方同 08-29 唤起修复）
                # + MB_SYSTEMMODAL 置顶（不依赖前台权限也悬浮最上层）
                fg = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
                cur_tid = kernel32.GetCurrentThreadId()
                attached = bool(fg_tid) and fg_tid != cur_tid and user32.AttachThreadInput(cur_tid, fg_tid, True)
                try:
                    ans = user32.MessageBoxW(None, '已截取对话区，是否识别入今日素材库？',
                                             'YY工具箱 · 素材采集',
                                             0x04 | 0x20 | 0x1000 | 0x00010000 | 0x00040000)
                    # MB_YESNO|ICONQUESTION|SYSTEMMODAL|SETFOREGROUND|TOPMOST
                finally:
                    if attached:
                        user32.AttachThreadInput(cur_tid, fg_tid, False)
            finally:
                with _SHOT_CONFIRM_LOCK:
                    _SHOT_CONFIRMING['on'] = False
            if ans != 6:                       # IDYES=6，其余（否/关窗）一律视为丢弃
                try:
                    png.unlink()
                    self.notify('YY工具箱 · 素材采集', '已丢弃该截图，未入素材库')
                except OSError:
                    pass
                return
            with _OCR_TASK_LOCK:
                _OCR_TASK.update(seq=_OCR_TASK['seq'] + 1, status='running', day=day, name=name, chars=0)
                seq = _OCR_TASK['seq']

            def _ocr():
                try:
                    t0 = time.time()
                    text = ocr_png(png).strip()
                    self._dbg(f'ocr done #{seq} in {time.time() - t0:.1f}s, {len(text)} chars')
                    n_chars = 0
                    if text:
                        png.with_suffix('.txt').write_text(text, encoding='utf-8')
                        n_chars = len(text)
                    with _OCR_TASK_LOCK:
                        _OCR_TASK.update(status='done', chars=n_chars)
                    self.notify('YY工具箱 · 素材采集',
                                f'识别完成（{n_chars} 字）→ 今日素材库' if n_chars
                                else 'OCR 未识别出文字，图已入库（生成日报时自动读图兜底）')
                except Exception as e:
                    self._dbg(f'ocr fail: {type(e).__name__}: {e}')
                    with _OCR_TASK_LOCK:
                        _OCR_TASK.update(status='done', chars=0)
                    try:
                        self.notify('YY工具箱 · 素材采集', 'OCR 识别失败，图已入库（生成日报时自动读图兜底）')
                    except Exception:
                        pass

            threading.Thread(target=_ocr, daemon=True).start()
        except Exception as e:
            self._dbg(f'shot fail: {type(e).__name__}: {e}')
            try:
                self.notify('YY工具箱 · 素材采集', f'截屏失败：{e}')
            except Exception:
                pass

    def report_ocr_poll(self) -> dict:
        """前端轮询后台 OCR 状态：seq 变化即有新截图或识别完成，前端刷新素材列表。"""
        with _OCR_TASK_LOCK:
            return dict(_OCR_TASK)

    def report_wechat_assets(self, day: str) -> list:
        """当日截屏素材列表 [{name, uri, text}]。uri = data URI（base64 内联，file:// 在
        pywebview 的 WebView2 中加载失败）；text = 同名 .txt 的本地 OCR 识别文本（无则空）。"""
        d = ASSETS_DIR / day if valid_day(day) else None
        if not d or not d.is_dir():
            return []
        out = []
        for f in sorted(d.iterdir()):
            if not (f.is_file() and f.suffix == '.png'):
                continue
            try:
                b64 = base64.b64encode(f.read_bytes()).decode('ascii')
                txt_f = f.with_suffix('.txt')
                text = txt_f.read_text(encoding='utf-8') if txt_f.is_file() else ''
                out.append({'name': f.name, 'uri': f'data:image/png;base64,{b64}', 'text': text})
            except OSError:
                continue
        return out

    def report_wechat_asset_delete(self, day: str, name: str) -> bool:
        if not valid_day(day):
            return False
        safe = Path(name).name
        if not safe.endswith('.png') or safe in ('.', '..'):
            return False
        p = ASSETS_DIR / day / safe
        try:
            ok = False
            if p.is_file():
                p.unlink()
                ok = True
            txt_f = p.with_suffix('.txt')      # 连带删 OCR 文本（删图留孤 txt 会成幽灵素材）
            if txt_f.is_file():
                txt_f.unlink()
            return ok
        except OSError:
            return False

    @staticmethod
    def _usage_add(prompt_t: int, completion_t: int, price_in: float, price_out: float):
        try:
            data = {'total_p': 0, 'total_c': 0, 'total_cost': 0, 'days': {}}
            try:
                data.update(json.loads(USAGE_PATH.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                pass
            day = time.strftime('%Y-%m-%d')
            d = data['days'].setdefault(day, {'p': 0, 'c': 0, 'cost': 0})
            data['total_p'] += prompt_t
            data['total_c'] += completion_t
            d['p'] += prompt_t
            d['c'] += completion_t
            cost = (prompt_t * price_in + completion_t * price_out) / 1e6
            d['cost'] = round(d.get('cost', 0) + cost, 6)
            data['total_cost'] = round(data.get('total_cost', 0) + cost, 6)
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            USAGE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        except OSError as e:
            Api._dbg(f'usage write fail: {e}')

    def hide_panel(self, from_blur=False):
        """失焦隐藏 / 启动工具后收起（JS blur 或点击卡片启动后调用）。
        pick_exe 的系统对话框弹出时 WebView 必然失焦——期间不隐藏。
        ⚠ 唤起宽限期（1.5s）：热键唤起后极短时间内的 blur 不是用户主动离开，
        而是前台应用单方面抢回焦点（实锤案例：带防切屏脚本的 Chrome 页面 1.8s 抢回，
        面板闪现即隐=用户报的"唤起后找不到"）；此情形把前台重抢回来一次。
        1.5s 内人类来不及点击其他窗口，不会误伤正常失焦隐藏；每个显示周期只重抢一次。
        ⚠ regrab 必须 self.visible=True（面板显示中）才允许：热键 hide 后 WebView 的
        blur 尾巴会异步到达，若不加此条件会把刚关掉的面板重新拉回（=用户实报
        "要点两次 Alt+Space 才能关闭"）。"""
        if self.pick_lock:
            return
        if (from_blur and self.visible and not self.regrabbed
                and (time.time() - self.shown_at) < 1.5):
            self.regrabbed = True
            self._dbg('blur within grace period -> regrab foreground')
            self._show_win()
            return
        self.visible = False
        self._hide_win()

    def notify(self, title: str, msg: str) -> bool:
        """Windows 原生 toast 通知（PowerShell + WinRT，番茄钟到点用）。
        脚本按 utf-8-sig 落盘规避编码坑；失败回落蜂鸣提示。"""
        ps = ("param([string]$Title = '', [string]$Msg = '')\n"
              "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
              " ContentType = WindowsRuntime] | Out-Null\n"
              "$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
              "[Windows.UI.Notifications.ToastTemplateType]::ToastText02)\n"
              "$txt = $tpl.GetElementsByTagName('text')\n"
              "$txt.Item(0).AppendChild($tpl.CreateTextNode($Title)) | Out-Null\n"
              "$txt.Item(1).AppendChild($tpl.CreateTextNode($Msg)) | Out-Null\n"
              "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
              "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
              ".Show([Windows.UI.Notifications.ToastNotification]::new($tpl))\n")
        try:
            ps_file = APP_DIR / 'data' / '_toast.ps1'
            ps_file.parent.mkdir(parents=True, exist_ok=True)
            ps_file.write_text(ps, encoding='utf-8-sig')   # BOM：PowerShell 5.1 中文安全
            r = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                 '-File', str(ps_file), '-Title', title, '-Msg', msg],
                capture_output=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW)
            ok = r.returncode == 0
            if not ok:
                self._dbg(f'notify failed: {r.stderr.decode("gbk", "ignore")[:200]}')
            return ok
        except Exception as e:
            self._dbg(f'notify error: {e!r}')
            return False

    def quit_app(self):
        """真正的退出（面板「退出」按钮）。
        ⚠ destroy() 在 5.4 走 WinForms Close() → FormClosing → 我们的"点 X 仅隐藏"
        拦截器返回 False → args.Cancel=True → 关闭被吃掉，进程不退、互斥体不释放
        （=用户实报"点了退出仍提示已在运行"，最小复现实测 quit_test.py）。
        修复：quit_lock 让 closing 放行 + 看门狗 2s 后 os._exit 强杀兜底。"""
        self.quit_lock = True
        try:
            if _G_HOTKEY:
                _G_HOTKEY.stop()
            if _G_SHOT:
                _G_SHOT.stop()
        finally:
            threading.Thread(target=lambda: (time.sleep(2), os._exit(0)),
                             daemon=True).start()          # 看门狗：destroy 卡住也保证退出
            if _G_WINDOW:
                _G_WINDOW.destroy()

    # ---- 供热键线程调用 ----
    def _is_really_shown(self) -> bool:
        """窗口真实可见 = 非最小化 且 位置在屏幕内（±32000 屏外是隐藏态）。
        不信 self.visible 标志：最小化时 Chromium 不一定发 blur → JS hide_panel 不执行
        → 标志漂移为 True，下次热键被误判成 hide（表现为按一下没反应）。"""
        if not self.hwnd or user32.IsIconic(self.hwnd):
            return False
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return False
        return rect.left > -10000 and rect.top > -10000

    def toggle(self):
        self._dbg(f'toggle called, visible={self.visible}')
        try:
            if not self.ensure_hwnd():
                self._dbg('toggle abort: no hwnd')
                return
            # 按窗口真实物理状态分支（visible 标志会因最小化不发 blur 而漂移，不可信）
            if self._is_really_shown():
                self.hide_panel()
                self._dbg('hide done')
            else:
                self.visible = True
                self._show_win()
                self.shown_at = time.time()   # 唤起宽限期起点（防前台抢占型应用秒抢回）
                self.regrabbed = False
                self._dbg('show done')
                # 刷新由 JS 端 focus 事件自感知（SetForegroundWindow 成功即触发）；
                # 热键线程调 evaluate_js 存在概率性卡死（阻塞消息泵致热键失灵），禁用
        except Exception as e:
            self._dbg(f'toggle error: {e!r}')

    @staticmethod
    def _dbg(msg):
        """调试日志（联调用，正式版可移除）：data/_toggle.log 追加。"""
        try:
            with open(APP_DIR / 'data' / '_toggle.log', 'a', encoding='utf-8') as f:
                f.write(f'{time.strftime("%H:%M:%S")} {msg}\n')
        except OSError:
            pass

    def ensure_hwnd(self):
        """确保已拿到窗口句柄：仅用标题枚举重试。
        不可访问 window.native.Handle——pythonnet 属性代理会递归遍历 .NET 对象图
        （启动日志的 Rectangle.op_Equality 错误即其产物），实测会破坏 WebView2 桥初始化。"""
        if self.hwnd:
            return self.hwnd
        for _ in range(20):
            self.hwnd = find_hwnd()
            if self.hwnd:
                break
            time.sleep(0.25)
        return self.hwnd


# ============================== 主流程 ==============================

def ensure_single_instance() -> bool:
    """命名互斥体保证单实例；已在运行返回 False。"""
    kernel32.CreateMutexW(None, False, 'YT_ToolBox_SingleInstance')
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


# 模块级全局：跨对象引用不挂在 Api 实例上（原因见 Api 类注释）
_G_HOTKEY = None
_G_WINDOW = None
_G_SHOT = None


def main():
    global _G_HOTKEY, _G_WINDOW
    if not ensure_single_instance():
        user32.MessageBoxW(None, '工具箱已在运行：按 Alt+Space 唤起面板。', 'YY工具箱', 0x40)
        return

    api = Api()
    window = webview.create_window(
        'YY工具箱',
        url=str(WEB_PAGE),
        js_api=api,
        width=940, height=800, min_size=(760, 520),   # 高 640→800（用户实锤部分区域展示不全，+25%）；客户区 924：三列卡片 882+边距 36 无横向滚动
    )
    _G_WINDOW = window

    def on_closing():
        """服务形式：点 X 仅隐藏面板（移屏外），进程与热键常驻；退出只走面板「退出」按钮。
        quit_lock=True 时放行（退出按钮的 destroy 走的是同一条 Close→FormClosing 链）。"""
        if api.quit_lock:
            return True       # 不取消关闭 → 窗口销毁 → webview.start 返回 → 进程自然退出
        api.hide_panel()
        return False          # 返回 False 拦截关闭，窗口存活

    window.events.closing += on_closing

    def on_ready():
        """窗口创建完成后：定位句柄 → 去任务栏图标 → 移屏外（启动即后台常驻）→ 注册热键。"""
        api.ensure_hwnd()
        if api.hwnd:   # 加 WS_EX_TOOLWINDOW：任务栏与 Alt+Tab 均不展示（唤起全靠热键）
            ex = user32.GetWindowLongPtrW(api.hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(api.hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW)
        api._dbg(f'ready, hwnd={api.hwnd}')
        api._hide_win()
        # 注意：不可在此处用 load_url 重载页面做"桥兜底"——pywebview 5.4 实测 load_url
        # 会击穿主窗口状态（后续 evaluate_js / js bridge 全线 'Main window failed to start'）
        global _G_HOTKEY
        _G_HOTKEY = HotkeyThread(api.toggle, api._dbg)
        _G_HOTKEY.start()
        global _G_SHOT
        if load_config().get('wechat_shot', True):   # 鼠标侧键截屏素材（设置里可关）
            _G_SHOT = ShotHookThread(api.on_shot_xbutton, api._dbg)
            _G_SHOT.start()

    webview.start(on_ready, gui='edgechromium')   # 必须显式 WebView2 后端（Trident 后端键盘事件失效）
    if _G_HOTKEY:
        _G_HOTKEY.stop()
    if _G_SHOT:
        _G_SHOT.stop()


if __name__ == '__main__':
    main()
