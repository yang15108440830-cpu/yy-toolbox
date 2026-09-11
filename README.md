# YY工具箱
> 全部自研工具的分组面板统一调取（目录名：工具箱启动器）：Alt+Space 全局热键唤起、拖拽分组持久化、自动发现新工具、后台服务常驻。

## 技术栈与版本
- Python 3.12.8 64位（D:\dev\env\Python312，venv 内置于本目录 .venv）
- pywebview 5.4（**锁定版本，勿升 6.x**，原因见已知限制第 1 条）+ WebView2（Win11 自带）
- pywin32 312（RegisterHotKey 全局热键 / Win32 窗口管理 / ExtractIconEx 图标提取）
- Pillow（exe 原始图标 HICON→PNG，缓存 data/icons/）
- 前端：web/index.html 单文件（原生 HTML5 Drag & Drop，无框架）

## 目录结构
```
工具箱启动器/
├─ app.py            # 入口：工具扫描(TOOLS.md+目录)、分组配置、热键线程、窗口管理、js_api桥
├─ web/index.html    # 面板前端：分组标签/卡片网格/拖拽/右键菜单/模态框
├─ web/bg/           # 背景图目录（放 jpg/png/webp 即生效；多张每次唤起随机；顶栏「背景」开关）
├─ data/
│  ├─ config.json    # 分组+待办+外部目录+上次分组+自定义应用（groups/ungrouped/todos/todo_history/external_dirs/active_group/apps/bg_enabled）
│  ├─ icons/         # 自定义应用图标缓存（exe 提取的 PNG，随移除清理）
│  ├─ _toast.ps1     # 番茄钟到点通知用 toast 脚本（运行时自动生成，utf-8-sig）
│  ├─ reports/       # 工作日报归档（YYYY-MM-DD.md，日历蓝点与「查看/编辑」数据源）
│  └─ _toggle.log    # 调试日志（联调观测用，git 忽略）
├─ .venv/            # 独立虚拟环境
├─ requirements.txt
├─ 启动.bat          # 日常启动入口（pythonw 后台常驻）
└─ README.md
```

## 启动方式
- 双击 `启动.bat`（pythonw 无黑窗后台启动，面板不弹出，按 Alt+Space 唤起）
- **开机自启**：已配置启动文件夹快捷方式（`shell:startup` 下的 `YT - YY工具箱.lnk`，直接指向 pythonw 零闪窗；取消自启删该 lnk 即可）
- 或命令行：`.venv\Scripts\pythonw.exe app.py`

## 端口
无（桌面工具，不监听端口）

## 交互一览
| 操作 | 效果 |
|---|---|
| Alt+Space | 唤起/隐藏面板（居中置顶，默认 920×640 恰好两行×三列卡片）|
| 点卡片 | 启动该工具，面板自动收起；**exe/bat/cmd 默认管理员运行**（每次弹 UAC 确认，点「否」=放弃启动；html/目录不提权）|
| 拖卡片到分组标签 | 跨组移动（即时写盘）|
| 组内拖卡片 | 排序 |
| 拖分组标签 | 分组排序 |
| ＋ 建组 / 右键标签 | 新建 / 重命名 / 删除组（组内工具移入未分组）|
| ＋ 应用 | 添加本地应用：exe（提取原始图标）/ html 网页（Web 卡片，启动走默认浏览器）→ 命名 → 卡片可拖分组（右键卡片移除，不动源文件）|
| ＋ 目录 | 添加文件夹：目录选择对话框 → 命名 → 琥珀色文件夹卡（点击资源管理器打开，右键可移除）|
| 待办「日历」 | 月历视图：有记录的日期带 `闭环/总数` 徽标（红=全未闭环/黄=部分/绿=全闭环）+ 底部蓝点=当天有日报，点日期看当天明细与日报入口 |
| 日报「生成日报」 | 分步向导：① 扫描本地仓库当日 git 提交（可勾选剔除）→ ② 贴微信聊天摘录 → ③ 贴 AI 对话摘要 → ④ 云端 AI 生成草稿 → 编辑定稿保存归档；⚙ 配置仓库列表/作者过滤/AI 接口（OpenAI 兼容）/另存目录；归档可一键另存到外部日报目录 |
| 点窗口 X | **仅隐藏**，服务常驻 |
| 面板「退出」按钮 | 真正退出进程 |

## 新工具自动适配
TOOLS.md 登记新工具（create-tool skill 流程）后，面板下次唤起自动出现在「未分组」。发现逻辑：解析 TOOLS.md 表格元数据 + 扫描根目录兜底（**release exe > 启动.bat > app.py > 目录内其他 bat**，2026-08-31 起打包 exe 优先（原 dist\，2026-09-02 迁移 release\）——不依赖 .venv/streamlit 环境且规避端口保留段坑；代价：源码迭代后需重新发布才会反映到面板启动）+ 扫描 external_dirs 外部目录裸 exe/bat，无需任何额外操作。

## 数据文件说明
- 位置：data/config.json
- 格式：`{"groups": [{"name": "组名", "tools": ["工具主键", ...]}], "ungrouped": [...], "external_dirs": ["外部目录路径", ...], "bg_enabled": true}`
- 工具主键：根目录工具=目录名（与 TOOLS.md 目录列一致）；外部目录工具=`ext:{exe文件名}`；自定义应用=`app:{路径md5前10位}`（防撞前缀）
- `external_dirs`：外部工具目录（如 D:\company\机器狗\自研工具），扫描其中所有裸 exe/bat，手工追加路径即可扩展
- 已删工具自动清出、新工具自动进未分组

## 当前状态：源码 ↔ release 同步性
无 exe 存档（纯源码运行；如需分发可后续 PyInstaller onefile 打包，注意 web/index.html 与 data/ 需随 exe 同目录分发）。

## 已知限制（联调实锤的坑，迭代前必读）
1. **pywebview 锁定 5.4**：6.2.1 存在 native 对象代理递归爆栈（`Rectangle.op_Equality` 错误串）+ 跨线程 show/evaluate_js 静默失败/延迟数十秒生效
2. **Api 实例严禁挂 pywebview 对象引用**（window/hotkey 等）：pywebview 初始化 js bridge 时深扫描 Api 属性，挂上 Window 会拖进 .NET 递归并炸死桥——跨对象引用一律走模块级全局（_G_WINDOW/_G_HOTKEY）
3. **load_url 禁用**：5.4 实测 load_url 会击穿主窗口状态（后续 evaluate_js/bridge 全线 'Main window failed to start'），勿用它做页面重载
4. **热键线程禁调 evaluate_js**：概率性阻塞消息泵 20 秒（热键失灵），页面刷新走 JS 端 focus/visibilitychange 事件自感知
5. **窗口"隐藏"用移屏方案**（SetWindowPos ±32000）而非 ShowWindow：pywebview WinForms 层在 WM_SHOWWINDOW 处理链上会使跨线程 ShowWindow(SW_SHOW) 延迟数秒生效
6. **bat 文件铁律：GBK 编码 + CRLF 换行**（Write 工具默认 UTF-8+LF 会炸——cmd 按 GBK 逐行解析，全角括号错位出半角 `)` 破坏 if 块；LF 引起多行块错位）。本工具启动.bat 已按此存储
7. 任务栏/Alt+Tab 无图标（WS_EX_TOOLWINDOW），唤起全靠 Alt+Space；如热键被其他软件抢占（面板内 hotkey 日志可查），面板就难以唤回——重启 启动.bat 即可
8. 多显示器：面板固定主屏居中（SM_CXSCREEN 只算主屏）
9. **create_file_dialog 两个 5.4 实测坑**：① 无 `webview.FILE_DIALOG_OPEN` 常量，dialog_type 直传 10，file_types 是 tuple 格式 `('描述 (*.exe)',)` 而非竖线字符串；② js_api 回调在独立 Python 线程（MTA）执行，WinForms ShowDialog 必须 STA——须起子线程 `pythoncom.CoInitialize()` 后调用，否则 ThreadStateException 被 pywebview 静默吞掉（前端表现为"没反应"）。另：对话框弹出必然触发 WebView blur，须用 pick_lock 拦住 hide_panel，否则选完文件命名框弹在屏外
13. **路径清洗铁律**（2026-08-31 实锤）：资源管理器「复制文件地址」自带 U+202A~U+202E 方向控制符，粘贴进文件对话框后混入路径 → `Path.is_file()` 恒 False。外部路径一律过 `clean_path()`（清方向符/首尾空白/引号）。另：`app_id_of` 入参兼容 str/Path（曾因 Path 无 .lower() 使 UI 添加流程全挂——无头验证传 str 未覆盖，UI 全链路必须至少真实点通一次）
14. **退出按钮会被 closing 拦截器吃掉**（2026-09-02 实锤修复）：`destroy()` 在 5.4 走 WinForms `Close()→FormClosing`，与点 X 同链——"服务形式"的 closing 拦截器返回 False → `args.Cancel=True` → 关闭被取消，进程不退、单实例互斥体不释放 → 下次启动永远"已在运行"。修复：`quit_lock` 标志让 closing 放行 + 看门狗线程 2s 后 `os._exit(0)` 兜底。最小复现实测：empty/工具箱启动器/quit_test.py（bug 版进程卡死 / fix 版自然退出）
10. **Win+D/Win+M 是唤起失效的元凶**（2026-08-29 实锤修复）：「显示桌面」会把 TOOLWINDOW 一并最小化，而 SetWindowPos 对最小化窗口无效（位置被系统钉在 -32000）→ 唤起"没反应"。且最小化时 Chromium 不一定发 blur，visible 标志漂移会让下次热键误走 hide 分支。修复三件套：`_restore_if_iconic`（SW_RESTORE 主路 + SC_RESTORE 消息兜底）+ `_force_foreground`（前台锁定时 Alt 合成 + AttachThreadInput 强抢）+ **toggle 按窗口真实物理状态分支**（非最小化且屏内=可见，不信 visible 标志）；show 后有 `show chk` 校验日志可诊断
11. **屏外隐藏会导致 WebView2 白屏**（2026-08-29 实锤修复）：Chromium 原生窗口遮挡检测（CalculateNativeWinOcclusion）把 -32000 屏外窗口判为 hidden 挂起光栅化，长时间（过夜/驱动重置）后移回屏内合成器恢复失败 → 整窗纯白但 JS 仍活着（纯白=WebView2 默认底色，非页面色）。修复：① `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-features=CalculateNativeWinOcclusion`（进程启动前设置，治本——不挂起）；② show 时 1px 尺寸抖动 + RedrawWindow(RDW_ALLCHILDREN)（治标兜底——已挂起也能强拉回合成器）。15 秒屏外挂起→唤起实测画面完整
12. **唤起后被前台应用"秒抢回"**（2026-08-31 实锤修复）：带防切屏/焦点抢占脚本的页面（如实测某巡检系统 Chrome 页 1.8s 抢回）会在面板唤起后瞬间夺走前台 → blur → 面板闪现即隐（=用户报"唤起后找不到"）。修复：唤起 1.5s 宽限期——期间 JS blur（hide_panel(true)）视为抢占而非用户离开，重抢前台一次（每显示周期仅一次，防与蜜罐页面 ping-pong）；1.5s 内人类来不及点击别窗，不误伤正常失焦隐藏。诊断工具：empty/工具箱启动器/blur_probe.py（100ms 高频观测 rect+前台窗口名）

## 迭代记录
- 2026-08-26 初始版本：Alt+Space 热键面板 + 拖拽分组持久化 + 工具自动发现 + 后台服务常驻（点 X 隐藏）+ 开机自启 + 任务栏隐身；联调修复 pywebview 桥死（Api 属性污染）、z 序置顶（TOPMOST→NOTOPMOST 配方）、存量 bat LF 隐患（根目录全部工具 bat 批量转 CRLF）
- 2026-08-26 集成外部工具目录：config.json 新增 external_dirs 机制，纳入 D:\company\机器狗\自研工具 四个 exe（MQTT调试/充电房门控制器/寻端/机器人模拟器）
- 2026-08-27 待办面板 + 分组记忆：下侧常驻待办（Enter 添加/闭环即删/历史保留 20 条可恢复）；工具区改两行列向流动横向滚动；记住上次打开分组；改名 YY工具箱（窗口标题/lnk/文档，目录名不变）
- 2026-08-27 UI 精美化（Fluent Design 体系）：双主题跟随系统深浅色（WinUI 3 官方色板，强调色 #0067C0/#4CC2FF）；Mica 模拟底（径向光斑 + feTurbulence 噪点）；卡片改图标容器布局（类型渐变图标 + 徽标）+ 35ms stagger 入场动画；弹窗/右键菜单 Acrylic（backdrop-filter）+ 缩放入场/出场动画；3px 细滚动条 + 横向滚动两端渐隐（溢出时才挂）；待办闭环淡出动画 + 创建/闭环时间戳；字体栈改 Segoe UI Variable + Microsoft YaHei UI。动效四档 83/150/250/300ms，入场 decelerate 出场 accelerate
- 2026-08-27 背景图功能 + 二轮美化：web/bg/ 放图即用（多张随机、竖图偏上取景），双主题差异化遮罩（浅 86% 保可读 / 深 70% 深蓝黑融夜景），顶栏「背景」开关持久化（bg_enabled）；卡片与待办容器 Acrylic 化（blur24 透出背景）；新增待办滑入动画、hover 图标微放、空状态图标
- 2026-08-27 自定义本地应用：＋ 应用按钮 → pywebview 原生文件对话框选 exe → 命名入库（config.apps，路径 md5 去重）→ ExtractIconEx+Pillow 提取原始图标缓存 data/icons/（无图标回落 🧩）；卡片右键移除（清分组归属+图标缓存，不动 exe）；新增依赖 Pillow；待办时间戳修复为本地 24 小时制（此前误切 UTC 串慢 8 小时）
- 2026-08-29 修复致命唤起失效（用户实报"Alt+Space 找不到面板"）：取证发现窗口 iconic=True——Win+D 把 TOOLWINDOW 最小化后 SetWindowPos 移屏完全无效；且最小化不发 blur 致 visible 标志漂移、热键误走 hide 分支。修复：show 前自动恢复最小化（SW_RESTORE + SC_RESTORE 兜底）、SetForegroundWindow 被拒时 AttachThreadInput 强抢前台、toggle 改按窗口真实物理状态（非最小化+屏内）分支、show 后写 show chk 校验日志。三轮最小化→热键压力验证全过；顺带修复文件对话框三层坑（无常量/file_types 格式/STA 要求，见已知限制 9）
- 2026-08-29 修复唤起白屏（用户实报"白屏啥内容都没有"）：截图取证+show chk 日志定位为 WebView2 屏外挂起后合成器恢复失败（纯白=WebView2 默认底色，JS 桥仍活着）。修复：禁用 Chromium occlusion 计算（WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS，须在 webview.start 前设置）+ show 时 1px 尺寸抖动强拉合成器 + RedrawWindow 全子窗口强制重绘 + 前台强抢加 Alt 合成解锁。15 秒屏外挂起→唤起截图验证界面完整（含背景图毛玻璃）
- 2026-08-29 三轮美化（截图迭代闭环：改版→截图→视觉评审→修正）：emoji 全换 Lucide 风格手绘 SVG 线条图标（Web地球/桌面显示器/脚本终端/应用拼块，白线稿配渐变容器）；卡片 hover 光泽扫过（550ms 斜向高光带）+ 阴影加强（静止 2px/6px、hover 8px/20px）+ 286px 三列填满消除右侧稀疏；唤起入场动画（scale+fade 250ms 每次可见重放）；遮罩减薄（浅 87→80%、深 70→64%，背景图更透出）；logo 加径向光斑双层质感；tabs 底 hairline 渐变分隔。注意：AI 视觉评审对 44px 小面积渐变色判读不可靠（曾误报"图标全浅青"），颜色争议用像素采样仲裁
- 2026-08-29 底部左右分割 + 番茄钟：窗口调 920×640（两行×三列卡片余量充足）；底部左待办（原功能）/ 右小工具区（WIDGETS 表驱动 tab，可扩展）；番茄钟（SVG 圆环进度+专注25′/休息5′点击切换+开始暂停续接重置；时间戳驱动计时，页面被 WebView2 节流至 1Hz 也不丢时；到点 PowerShell+WinRT 原生 toast 通知，脚本 utf-8-sig 落盘）；修复添加应用两处体验坑：对话框关闭瞬间 blur 竞态藏面板（前端 suppressHide 抑制）、失败场景静默无提示（pick_exe 区分取消/异常，异常 toast）。AweSun 案例结论：homePC 不存在（实为 HomePC.lnk），对话框只筛 *.exe，应选 AweSun.exe
- 2026-08-31 待办日历 + 记事本多页/富文本完善 + 唤起抗抢占：待办「日历」按钮弹月历（创建日/闭环日聚合徽标计数、点日期看当天明细、‹›翻月、今天描边）；记事本多页（notes_pages/notes_page 持久化、◀▶翻页＋建页✕删页、末页删除清空保底、页码记忆）+ 富文本工具栏（B/I/S/列表/三档字号/清除格式，execCommand，粘贴转纯文本）+ 编辑器为进程内事实源防唤起回填竞态；番茄钟 ⚙ 时长配置（1-180/1-60 校验、持久化、空闲即生效计时中不打断）；窗口 940 宽消除三列溢出滚动条；**唤起宽限期 1.5s 抗前台抢占**（已知限制 12，blur_probe.py 实锤微信/巡检页面秒抢回场景）；自动验证方法论沉淀：截图+像素采样仲裁 AI 视觉评审、toggle+blur 竞态下测试脚本需"循环唤起+点击钉焦点"
- 2026-08-31 修复三个添加应用潜伏 bug：① 日历徽标改 done/total 三色（红全未闭环/黄部分/绿全闭环）；② 关一次关不掉——hide 后 blur 尾巴误触发宽限 regrab 把面板拉回（加 self.visible 前置，hide_race_test.py 单测实锤）；③ 添加 exe 必失败——U+202A 脏路径（clean_path 清洗）+ app_id_of 收 Path 无 .lower()（初版即有，UI 链路从未真实点通所致）；外部扫描重复文件允许共存添加（原版图标卡）+ note 提示；save_app 返回结构化 {ok, why, note} 前端精准提示
- 2026-08-31 闭环系统"打不开"根因修复 + 挂载策略改 dist 优先：① winnat 动态保留段（8468~8567）吞掉 8501/8502 → Streamlit 绑定失败（netstat 无占用是关键特征），全线迁移 8501→8601、8502→8602（bat/README/TOOLS.md/run_app.py 同步，excludedportrange 用 netsh 查）；② find_target 优先级改 dist exe > 启动.bat（用户要求挂打包 exe，LogView/闭环系统/自动关机现挂 dist exe），打包后 exe 内嵌旧端口逻辑需重新打包才生效；③ html 支持添加为应用（Web 卡片走默认浏览器）
- 2026-09-03 工作日报功能：底部小工具区新增「日报」tab + 分步向导（①本地仓库 git log 扫描当日提交（`--author` 过滤，默认 git 全局邮箱，可勾选剔除）→②微信聊天摘录粘贴→③AI 对话摘要粘贴→④云端 AI 生成草稿）→编辑定稿→按日归档 data/reports/YYYY-MM-DD.md。设计要点：微信 4.1（本机实锤版本）本地库 SQLCipher 加密，自动读取需读进程内存提取密钥（侵入强/随版本失效/杀软风险），经用户确认摘录走粘贴框；AI 走 OpenAI 兼容接口（标准库 urllib 零新依赖，base_url/api_key/model 三项可配，超时 60s/网络错误重试 1 次/4xx 直接失败返回 why，key 不入日志）；git log 用 %x1f 单元分隔符分列防 subject 含 | 切错列；日报文件名日期过正则白名单防路径注入；日历加"有日报"底部蓝点 + 明细区查看/编辑入口（换日期即时同步当日归档防覆盖）；向导与设置共用 #modal 单例（设置返回重放骨架，素材数据存 REP 对象不丢）。无头验证 32 项全过（empty/工具箱启动器/report_test.py，config/归档目录 monkeypatch 隔离）；UI 全链路点通验证受阻于机器锁屏（截屏取证为安全桌面），待解锁后人工自验。测试方法论补充：锁屏下 SendKeys/keybd_event 合成 Alt+Space 无法触发 RegisterHotKey、CUA 截屏不可用，须用 PowerShell CopyFromScreen 截屏 + Read 查看取证
- 2026-09-03 修复日报向导两个首用 bug（用户实报"点生成草稿后有提示但看不清"）：① toast z-index 70 低于模态遮罩 100 且遮罩带 20px 背景模糊——模态期的提示气泡成模糊黑影完全不可读，toast 提到 z-110；② 步骤④漏放「AI 生成草稿」按钮——步骤③的「生成草稿 →」只是翻页进草稿页，页内 hint 所指的按钮不存在，AI 生成无入口（修复：foot 加 #rw-gen 按钮绑 repGenerate，仅步骤④显示）。教训：向导类 UI 每个 hint 提到的操作必须有真实对应控件，且 toast 必须全层级可见
- 2026-09-03 修复向导首用流程第二坑（用户实报"配置了仓库仍提示三处都留空"）：步骤①扫描不自动执行——用户配完仓库直接下一步，REP.scan 空，步骤③被"素材全空"拦截。修复：进入步骤①自动扫描（repScan 抽函数 + scanBusy 防重入，配置保存返回向导自动重扫，换日期自动重扫）；拦截提示改分场景文案（扫描中/微信AI摘要空但提交有/仓库当日无提交）——笼统提示让配置正确的用户误以为配置没生效。scanBusy 防重入原因：自动扫描是 fire-and-forget 异步，连点或快速翻页会并发多次 report_scan_commits
- 2026-09-03 修复向导首用流程第三坑（用户实报"扫描有提交仍拦截微信AI摘要空"）：步骤①提交勾选状态存在 checkbox DOM 里，翻页 innerHTML 重绘即焚——repCollected() 在步骤②③查的是当前页 DOM（无 checkbox）恒为空，AI 调用同病。修复：勾选状态持久化 REP.pickedKeys（Set('ri:ci')，null=未交互=全选），checkbox change 实时同步、重渲染按其恢复、repScan 后重置；repCollected() 改纯数据计算与 DOM 解耦（静态断言防回归）。教训：分步向导的中间态一律入状态对象，禁止依赖会被整帧重绘销毁的 DOM
- 2026-09-03 修复 AI 端点拼接 404（用户实报"生成草稿 HTTP 404 path=/v4/v1/chat/completions"）：ai_endpoint 旧规则假设所有厂商 base_url 以 /v1 结尾、否则强插 /v1——智谱地址 /api/paas/v4 被拼成 /v4/v1/chat/completions。修复：按 urlparse 是否有路径段分流——带路径段（/v4、/v1、/compatible-mode/v1）直接拼 /chat/completions，仅裸域名补默认 /v1（DeepSeek 官方裸域名兼容 /v1 路径）。无头用例改为预设四家真实 base_url 全覆盖。教训：OpenAI 兼容端点的版本段各家不一致（/v1、/v4、/compatible-mode/v1、无），URL 后处理只能按"有无路径"分流，禁止假设特定版本段
- 2026-09-03 AI 生成改流式 + 实时思考面板（用户反馈"汇总提示太丑、想看 AI 思考过程"）：① 后端 ai_chat（阻塞式）改 ai_chat_stream——SSE 流式解析 delta.content 与 delta.reasoning_content（智谱 GLM/DeepSeek 思考模型的思考过程字段），任务跑后台线程写模块级任务槽（单槽+锁），新增 report_ai_start/report_ai_poll 两个 js_api（js_api"调用-返回"模型塞不进流式进度，前端 600ms 轮询全量累计文本——不引入 evaluate_js 推送，避开已知限制 4 雷区）；② 前端生成中在编辑框上盖 Acrylic 实时面板：spinner 动画 + 思考过程等宽小字自动滚底（模型无思考输出自动隐藏思考区），标题按阶段切换"AI 正在思考…/正文生成中…"，生成中三按钮禁用、关向导清轮询定时器；断流时已生成部分回填编辑框；③ 顺带修 foot 布局 bug（用户截图实锤）：state 与按钮被 flex 压缩成竖排字——按钮 nowrap+flex:none、state ellipsis。无头新增本地伪 SSE 服务器用例验证流解析（思考字段/多段合并/注释行跳过）
- 2026-09-03 素材增强：日报 AI 表述升级（用户反馈"统计过于简单"）——git 扫描每条提交附带改动规模、涉及模块、提交说明（%b 压单行限 300 字）；prompt 升级为"按工作主题聚类合并同类提交、研发视角表述（做了什么/解决什么/影响范围），严禁照抄提交标题"。两个 git 实锤坑：① `--shortstat` 与 `--name-only` 同给时 diff 输出格式单选、后者吞前者（stat 全空），改用 `--numstat` 一份输出同时拿行数与路径、自行汇总；② merge 提交默认无 diff 输出（用户当日提交恰是 merge），须 `-m --first-parent` 相对第一父取 diff。dirs 取路径前两段（Java 深包全路径会撑爆素材）；numstat 增删合计与官方 shortstat 逐字节核对过（42/49）。前端提交行尾显示改动统计小字、hover 出提交说明，辅助勾选决策
- 2026-09-03 微信素材身份区分（用户实锤聊天记录格式：`发送者名称\nYYYY年MM月DD日 HH:MM\n消息内容` 逐条，无法区分谁在说话）：设置加「微信昵称」配置项（report_wechat_name），组装素材时在微信素材标题标注本人身份+prompt 注入发言者区分规则（本人发言=自己的工作安排；他人发言中向本人提出的需求/任务/问题是今日工作重要来源）；未配置昵称时素材头降级标注"无法可靠区分发言者"且不注入规则（防 AI 乱猜身份）。步骤②粘贴框 hint 同步提醒配置昵称
- 2026-09-03 日报工作台升级（用户拍板 D 方案+顶部今日条+四维度统计）：① 日历点已归档日报直达编辑页（原落在步骤①要走三步，形同纯展示）；② 面板 header 下新增极薄「今日概览条」（提交/闭环/专注/日报/AI花费 五个数字即按钮，点击分跳向导/历史待办/番茄钟/今日日报/设置），一行放全（5 项×~70px < 940 宽）；③ 日报 widget 改看板+最近日报流：今日 git（含 +行/-行）·专注分钟·日报状态 + 最近 3 天日报（正文首行预览，点任意天直达编辑）；④ 四维度自动统计：git 量化（report_today_stats 后端 60s 缓存，数据复用 scan_repo_commits 数值字段）、待办闭环（前端 config 时间戳直算零成本）、番茄钟时长（原不落盘——pomoFinish 落 config.pomo_log 只保 60 天）、AI token/花费（流式 usage 记账 data/usage.json 按日+累计，花费按记录时点单价折算防价格漂移，设置页填输入/输出单价 元/百万tokens 后生效，顶部条显示今日金额或 token 数）；⑤ 日报生成注入「素材四：本机工作量化数据」帮 AI 体现实工作量；⑥ 智谱等流式 usage 靠 stream_options.include_usage。无头 50/50（新增统计缓存/记账金额/最近流用例）
- 2026-09-03 顶部条点击行为细化（用户指定）：点「闭环」只看今日闭环（新增 showTodayClosed 过滤 closed_at 为今天的条目，历史全量仍在待办面板「历史」按钮）；点「提交」看按项目分组的今日提交明细（新增 showCommitsView：仓库分组头+时间/版本/提交信息三列，不含代码 diff，悬停出提交说明；数据复用 report_scan_commits），日报 widget 的提交数字同行为
- 2026-09-04 微信素材采集定版：鼠标侧键截屏（用户拍板放弃解密库路线——可行性报告结论：4.1.11+ 密钥格式变更需 Frida spawn 注入 + 版本专属偏移逆向 + 杀软对抗 + 每次提密钥重启微信，成本收益比不支持；调研详见 2026-09-03 迭代记录与 wechat-4.1.12-decrypt 项目文档）。实现：WH_MOUSE_LL 低级钩子线程监听 XBUTTON1/2 → 截前台窗口（BitBlt 屏幕 DC；副屏整体窗口拒截为 V1 已知局限）→ data/reports/assets/日期/HHMMSS.png + 系统 toast 确认；不吞鼠标事件（CallNextHookEx 照传，侧键原功能保留）；回调快返回铁律（截图丢工作线程，LL 钩子超时会被系统摘钩）。生成日报时最近 5 张转 base64 走 OpenAI 兼容视觉消息（image_url data URI，需视觉模型如 glm-5.3-flash）；向导步骤②改素材库（缩略图/悬停删除/文字粘贴兼容）；设置加侧键截屏开关（改后重启生效）。无头 58/58（截屏真实前台窗口/路径穿越防护/伪 urlopen 拦截验证视觉消息构造）。教训：无头测试漏 monkeypatch USAGE_PATH 污染真实记账文件（跨午夜后断言失败暴露），路径类全局一律全量隔离
- 2026-09-04 修复日报界面两处样式 bug（用户截图实锤）：① widget 最近日报流文字溢出边界——根因 `.widget` 的 `align-items:center` 使子项宽度收缩为内容宽，nowrap 摘要把整条链撑出容器（ellipsis 规则形同虚设），`#w-report` 覆盖为 `align-items:stretch` 拉满宽度后截断生效；② 素材缩略图破图——文件本身完好（Edge headless 实测相对路径可加载），改后端返回 base64 data URI 内联绕开 WebView2 的 file:// 限制 + img onerror 显示"加载失败"可诊断。排查方法论：CSS 括号配平/规则存在性检查均正常时，用 headless 浏览器对最小复现页实测区分"路径问题 vs 渲染环境问题"
- 2026-09-04 日报数据源省 token 改造（调研定版方案一，用户拍板）：微信截图素材**本地 OCR 文本化**——新增依赖 rapidocr-onnxruntime（PaddleOCR 模型 ONNX 纯离线，~60MB）。选型依据（本机实测同一张微信对话截图）：Windows 内置 OCR（Windows.Media.Ocr via PowerShell WinRT）中文小字错字率 ~30% 不可用；RapidOCR 错字率 <2%（37 行与原图逐字基本一致）、热识别 2.4s/张。流程：侧键截屏 → 后台 OCR（引擎惰性单例，首次加载 ~5s）→ 文本存同名 .txt + toast 报字数 → 生成日报时素材二 = 粘贴摘录 + 〔截图素材〕OCR 文本段，不再发图（token 省 90%+）；OCR 失败/缺失的图自动降级走视觉兜底（封顶 5 张）。素材删除连带删 txt；素材列表接口带 text 字段（前端标注"已识别为文字"）。排查坑：① 网上流传的 WinRT OCR 教程类型名错误，正确为 System.WindowsRuntimeSystemExtensions；② Git Bash(mSYS) 下中文 argv 传 PowerShell 丢失（pythonw 部署环境不受影响，测试用 ASCII 路径绕过）；③ PowerShell 5.1 stdout 按 GBK 解码。无头 63/63（含 OCR 真实识别/素材组装/连带删除）
- 2026-09-04 调研备查：微信聊天记录导出工具（LC044/WeChatMsg 留痕等）主打 3.x，4.x 加密变更后仍绕不开 Frida 解密路线（见 09-03 可行性报告），维持不可行判定；搜索配额限制，GitHub 项目星数/活跃度待恢复后补证
- 2026-09-04 素材缩略图破图终修（file:/// 绝对 URI 仍失败 → 根因锁定为 pywebview 的 WebView2 环境对 file:// 子资源加载受限：裸 Edge headless 加载同路径正常，工具箱内核失败，机制未查明）。终方案：report_wechat_assets 直接返回 base64 data URI 内联（不经过任何文件访问层），单图 ~百 KB 量级列表传输无压力；img onerror 显式"加载失败"诊断保留；视觉素材上限 5→20 张（用户反馈偏少；glm-5.3-flash 上下文充足且按所填单价 20 张图仅几分钱）
- 2026-09-04 向导步骤③改名「AI 摘要」→「其他事项」（用户反馈取名歧义）：定位扩展为补充 git/微信之外的零散工作——领导临时安排（调试网络）、面试/接待、与 AI 协作摘要等；hint 给条目示例，后端素材三标题同步改为"其他工作事项补充"
- 2026-09-04 素材库图片预览：缩略图点击放大——独立 #img-viewer 全屏层（毛玻璃遮罩+大图居中，z-105 介于模态与 toast 之间，独立于 #modal 避免顶掉向导），点击任意处/Esc 关闭，悬停缩略图显示 zoom-in 光标
- 2026-09-04 侧键截屏只截微信对话区（用户要求防无关内容入镜）：微信 4.1 自绘 UI 不暴露内部布局（UIA 实测仅 3 元素），自动定位聊天区不可行——改固定裁左方案：截屏时按 `shot_crop_left`（默认 300px≈左图标栏+会话列表栏）裁掉左侧，量在设置「截屏裁左」可调（0=整窗，0-800 夹紧，裁后过窄回退整窗报错），实拍验证 1928→1628 宽生效；用户实测 300 仍残留列表碎片，按截图估算上调默认 430（430 ≈ 图标栏 64 + 列表栏 ≈366，配置即时生效无需重启——on_shot_xbutton 每次现读 config）；用户实测 430 裁过头，终调 335
- 2026-09-03 日报设置体验升级：① 仓库列表改浏览添加——「＋ 浏览添加仓库」调系统目录对话框（pick_dir 加 check_dup 参数：日报仓库与自定义应用是两个体系，命中 apps 查重会拿不到路径），列表化展示逐条 ✕ 移除，另存目录同加「浏览」；② AI 厂商下拉自动填 URL——预设智谱/DeepSeek/通义千问/Kimi（base_url+模型 ID 均 2026-09 官方文档实检：glm-5.3 系列、deepseek-v4 系列、qwen3.8 系列、kimi-k3/k2.7 系列；旧名 deepseek-chat/kimi-k2 系列已从各家文档下架勿回填；Anthropic 区域封锁未取证不进表），用户只输 API 密钥+下拉选模型；已存 base_url 反查厂商回显，匹配不到落「自定义」保底回填；预设更新后配置里的旧模型名保底列出防静默丢失。JS 块注释内含 `k2-*/` 序号会把 `*/` 提前闭合注释（node --check 实锤），注释里勿写星号+斜杠序列
- 2026-09-04 日报草稿五项体验定版（用户实报 + subagent 三路分析定因汇总）：① **素材传参 bug 修复（OCR 进不了日报的根因实锤）**——前端 repGenerate 把 report_wechat_assets 返回的完整对象数组原样传给 report_ai_start，后端按纯文件名解析（Path(str(dict)).name 不以 .png 结尾）continue 把全部素材静默丢弃，OCR 文本与视觉兜底双双进不了 prompt；前端改传文件名数组 + 后端兼容 {name,...} 对象双保险。② **侧键截屏异步化**——原实现截屏→OCR→存txt→toast 串行（首次含引擎加载 ~5s）用户须停留干等；改截屏成功立即 toast「可继续操作」，OCR 丢后台线程（推理全程持 RLock 串行防连按并发跑模型），完成再 toast 字数并推进 _OCR_TASK.seq，前端步骤② 1.5s 轮询 seq 自动刷新素材列表（离开步骤②/关弹窗清定时器）。③ **日报体例定版**——prompt 四节结构（今日完成/微信工作沟通要点/其他事项/问题与风险）删除明日计划节；提交素材不拼 stat 行数、量化块去「+N/-M 行」、prompt 显式禁止代码量统计入正文（改动统计仅供 AI 判断工作量）。④ **日报 SQLite 权威存储（年度述职数据源）**——data/reports.db（sqlite3 标准库零依赖），reports 表含 content/summary/updated_at + 按日量化快照列（commits/ins/dels/repos/pomo_min/todo_closed/tokens/ai_cost/assets_cnt/exported）保存日报时同步快照，md 文件降级为人工查看/外部流转副本；首次使用自动迁移 data/reports/*.md 旧档入库（幂等，重装不丢历史），report_get/dates/recent/export 全部改读库（md 兜底），年度述职可直接 SELECT 聚合全年量化报表。⑤ **markdown 预览渲染**——内置零依赖 mdToHtml（标题/列表/加粗/行内码/段落子集，工具纯离线不引 CDN），步骤④加编辑/预览切换按钮，已归档日报打开默认预览态；顺带修 repSave 读隐藏 textarea 隐患（统一以 REP.text 为源）+ summary 剥 ** 星号（迁移实锤列表预览裸露星号）。无头 79/79（新增拦截 ai_chat_stream 捕获 prompt 验证素材链路/行数禁令/量化块无行数、DB 往返与 md 迁移用例）。方法论：跨前后端数据流 bug 用「参数契约逐段核对」定位（前端对象数组 vs 后端期望字符串），复杂多点改造先 subagent 分路取证再汇总实施
- 2026-09-07 侧键截屏加确认框（用户拍板 Windows 原生弹窗形态）：按侧键 → 截屏 → 原生 MessageBox「已截取对话区，是否识别入今日素材库？」（MB_YESNO|ICONQUESTION|SETFOREGROUND|TOPMOST，工作线程阻塞等选择、置顶保微信等任何前台可见）→「是」后台 OCR（异步化流程不变，完成 toast 字数）；「否」/关窗一律删除该截图不入库不识别（防误触截图污染素材库）。确认框挂着时忽略新侧键（_SHOT_CONFIRMING 互斥，防多框叠加）。MessageBoxW 按 64 位铁律补 argtypes/restype 声明。无头 84/84（mock MessageBoxW/截屏/OCR/toast 验证 确认落库/拒绝删图/互斥忽略 三分支）
- 2026-09-07 修复确认框后台弹不出（用户实锤"工具箱在后台时弹窗显示不出来"）：后台/屏外进程无前台权限，Windows 前台锁定把 MessageBox 压成任务栏闪烁不显示。双保险修复：① AttachThreadInput 借当前前台线程输入队列获得弹窗前台权限（配方同 08-29 唤起修复，弹后立即 detach）；② 加 MB_SYSTEMMODAL 置顶（不依赖前台权限也悬浮最上层，不激活不抢焦点）。无头 84/84 回归通过
- 2026-09-08 修复设置弹窗连带关闭日报向导（用户实锤"关闭模型设置把日报弹窗也关了，要重新生成"）：时序竞态实锤——closeModal 用 160ms 延迟回调摘 show，而设置关闭 60ms 后就重建向导，延迟回调晚于向导重开执行把刚显示的弹窗又关掉。修复：closeModal 的延迟句柄存 modalCloseTimer，新增 reopenModal()（清挂起回调+移除 closing+恢复 show），设置返回向导（保存/取消两路 leave）一律走它。方法论：模态出/入场动画驱动的开关状态不能只看类名同步逻辑，必须核对异步回调与后续重开的时序窗口
- 2026-09-08 日报正文限长（用户定版：≤150 字、目标 80 字左右）：prompt 加长度硬约束（每节至多 1-2 条、每条一句话、删修饰铺垫），REPORT_BODY_HINT「逐条列举」同步收紧为分组短句。无头 85/85
- 2026-09-08 修复日报未保存草稿丢失（用户二次实锤"退出模型设置后日报界面编辑的文本都不在了"）：双保险修复——① **REP.drafts 按日草稿缓存**：编辑 input/AI 生成回填（done 与断流部分保留两路）实时写缓存，保存归档成功即清（保证 draft 存在必然比归档新），openReport 与步骤①换日期一律 draft 优先于归档加载（有 draft 回编辑态，纯查看仍默认预览态）——无论弹窗被哪条路径整体关闭，重开都能恢复编辑现场；② **设置退出三路加固**：保存/取消去掉 60ms setTimeout 延迟改同步 leave（消除与 closeModal 出场动画收尾的竞态窗口），补 Esc=取消（设置界面此前无 Esc 处理，三路都走 leave 保证从向导进来必返回向导）。方法论：状态丢失类 bug 与其逐一追竞态路径，不如把"未保存态"显式持久化到会话级缓存，让所有关闭/重开路径天然兜底
- 2026-09-08 主面板默认高度 640→800（+25%，用户实锤部分区域展示不全）；宽度与三列卡片布局不动（客户区 924 无横向滚动），前端右键菜单位置为 innerHeight 动态计算无需同步
- 2026-09-08 日报向导弹窗宽度 580→650px（+12%，用户要求加宽编辑区）；「重新扫描」按钮从步骤①顶部行移到弹窗底部栏左下角（常驻 foot、仅步骤①显示，绑定移 buildReportShell 防重复绑定）
- 2026-09-09 维护历史日报直达（用户拍板「选日期直达编辑」）：步骤①换日期时该日已有归档或未保存草稿 → 跳过步骤②③空走直达编辑页（draft 优先、有草稿回编辑态）；widget 最近日报流 3→7 条作主要翻查入口；顺带清掉上一轮遗留：renderRepStep1 内对 foot 按钮 #rw-scan 的重复绑定
