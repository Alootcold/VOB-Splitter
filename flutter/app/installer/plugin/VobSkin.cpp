// ---------------------------------------------------------------------------
//  VobSkin —— NSIS 插件：用 Duilib 承载安装界面
//
//  NSIS 脚本本身画不了界面，这一段是「界面层」：
//  插件在 NSIS 进程里创建一个 Duilib 窗口，NSIS 脚本通过下面这组命令驱动它。
//
//  插件与 NSIS 的约定（NSIS 3 的调用约定，5 个参数）：
//      void __stdcall Fn(HWND hwndParent, int stringt, TCHAR* vars,
//                        void* stacktop, extra_parameters* ep)
//    * hwndParent —— NSIS 主窗口
//    * stringt    —— 字符串缓冲区长度（NSIS_MAX_STRLEN）
//    * vars       —— $0..$9 / $R0..$R9 变量区
//    * stacktop   —— NSIS 栈顶指针（插件的 Push/Pop 与脚本的 Push/Pop 共用同一个栈）
//    * ep         —— 里面是 ExecuteCodeSegment（回调脚本）与 RegisterPluginCallback（保活）
//
//  两个必须记住的坑：
//
//  1) NSIS 压插件参数时，**第一个参数在栈顶**，所以按书写顺序弹，不是反序。
//
//  2) NSIS 在每次插件调用结束后会卸载插件（Plugins_CanUnload）。
//     不注册 callback 的话，每次调用都是一个全新的模块实例 —— 窗口建在一个
//     实例里，后续的 SetSkinCaption / BindSkinCallback 却落在另一个实例上，
//     全是空操作。所以 InitSkin 里必须 RegisterPluginCallback。
//
//  消息循环在插件里（RunSkin 会一直转，直到脚本调用 Finish / Quit）：
//  界面要续响应点击、进度条要能实时刷新，消息就不能只在 NSIS 解释器空闲时
//  才被派发。脚本回调由这个循环发起 —— 每次回调都是一次独立的
//  ExecuteCodeSegment，解释器不会嵌套在自己里面。
//
//  脚本回调的序号：
//  NSIS 的 GetFunctionAddress 返回的是「函数序号 + 1」（见 NSIS 的 EW_CALL），
//  所以插件保存这个值，回调时调用 ep->ExecuteCodeSegment(序号 - 1, NULL)。
//
//  注意：本文件必须存成 **UTF-8 with BOM**。
//  没有 BOM 时 MSVC 会按系统 ANSI（中文机 = GBK）解码，中文注释里的字节
//  会把注释结构搞坏，编译出一堆莫名其妙的语法错误。
// ---------------------------------------------------------------------------

#include <windows.h>
#include <tchar.h>
#include <stdio.h>
#include <string>
#include <map>

#include <shobjidl.h>

#include "UIlib.h"
#include "sdk/api.h"

using namespace DuiLib;

namespace {

// NSIS 的栈元素：{ next, text[NSIS_MAX_STRLEN] }
// 这里只声明到 text[1]，实际分配时按 stringt 补齐，布局与 NSIS 内部一致。
struct NStack {
    NStack* next;
    TCHAR text[1];
};

// NSIS 栈桥接：插件的参数从栈里取，返回值压回栈里。
class NsisBridge {
public:
    NsisBridge(int stringt, void* stacktop)
        : m_strlen(stringt), m_stack(static_cast<NStack**>(stacktop)) {}

    // 弹出一个字符串（NSIS 把第一个参数放在栈顶，所以按书写顺序弹）
    bool Pop(LPTSTR buf, int cch) {
        if (!m_stack || !*m_stack) return false;
        NStack* th = *m_stack;
        lstrcpyn(buf, th->text, cch);
        *m_stack = th->next;
        GlobalFree((HGLOBAL)th);
        return true;
    }

    bool PopInt(int* out) {
        TCHAR buf[64];
        if (!Pop(buf, 64)) return false;
        *out = _ttoi(buf);
        return true;
    }

    void Push(LPCTSTR s) {
        // 注意：栈空的时候也必须能压入。
        // 之前这里写成 if (!m_stack || !*m_stack || !s) return;，
        // 弹完参数栈正好空了就不压了，脚本 Pop 拿到的是上一次的残留值。
        if (!m_stack || !s) return;
        size_t bytes = sizeof(void*) + static_cast<size_t>(m_strlen) * sizeof(TCHAR);
        NStack* th = static_cast<NStack*>(GlobalAlloc(GPTR, bytes));
        if (!th) return;
        lstrcpyn(th->text, s, m_strlen);
        th->next = *m_stack;
        *m_stack = th;
    }

    void PushInt(int v) {
        TCHAR buf[32];
        _stprintf_s(buf, 32, _T("%d"), v);
        Push(buf);
    }

private:
    int m_strlen;
    NStack** m_stack;
};

typedef std::basic_string<TCHAR> TStr;

TStr ToStr(LPCTSTR s) {
    return s ? TStr(s) : TStr();
}

// 无边框窗口的样式。
//   * 不要 WS_CAPTION / WS_THICKFRAME —— 否则窗口有系统边框。
//   * 不要 WS_MAXIMIZEBOX —— 否则标题条双击会把窗口最大化，
//     而界面是固定尺寸的，最大化之后是一副散架的样子。
//   * 保留 WS_SYSMENU | WS_MINIMIZEBOX —— 最小化按钮才有意义。
//   * 再加 WS_EX_APPWINDOW —— 皮肤窗口是 NSIS 主窗口的子窗口，
//     不加这个的话最小化之后任务栏上没有入口，窗口就找不回来了。
const DWORD kSkinStyle = WS_VISIBLE | WS_SYSMENU | WS_MINIMIZEBOX;
const DWORD kSkinExStyle = WS_EX_APPWINDOW;

// 解析 "x,y,w,h" 这样的整数列表。
// 不用 sscanf：Unicode 下格式串会变成宽字符，ANSI 的 sscanf 会读错。
bool ParseIntList(LPCTSTR s, int* out, int count) {
    if (!s) return false;
    LPCTSTR p = s;
    for (int i = 0; i < count; ++i) {
        while (*p == _T(' ') || *p == _T(',')) ++p;
        if (*p == 0) return false;
        TCHAR* end = NULL;
        long v = _tcstol(p, &end, 10);
        if (end == p) return false;
        out[i] = (int)v;
        p = end;
    }
    return true;
}

// 把控件树的位置写成一个文本文件（自动化测试用来找按钮坐标）。
// 定义在文件末尾，这里先声明。
void DumpControlRects(CControlUI* ctl, HANDLE f);

// ---------------------------------------------------------------------------
//  皮肤窗口
// ---------------------------------------------------------------------------
class SkinWindow : public WindowImplBase {
public:
    SkinWindow()
        : m_hwnd(NULL), m_owner(NULL), m_icon(NULL), m_ep(NULL),
          m_done(false), m_continue(false), m_lastCallback(0),
          m_inCallback(false) {}

    LPCTSTR GetWindowClassName() const { return _T("VobSkinWindowClass"); }
    CDuiString GetSkinFolder() { return m_folder; }

    // Duilib 读 XML 时会把「资源路径」拼在文件名前面
    // （CMarkup::LoadFromFile 里是 sFile = GetResourcePath() + pstrFilename），
    // 所以这里给相对文件名，目录由 resourcePath 决定。
    CDuiString GetSkinFile() { return m_file; }

    void Setup(HWND owner, extra_parameters* ep, LPCTSTR folder, LPCTSTR file,
               LPCTSTR iconPath) {
        m_owner = owner;
        m_ep = ep;
        m_folder = folder ? folder : _T("");

        // Duilib 默认把皮肤目录拼在「exe 所在目录」后面，而我们的皮肤在
        // $PLUGINSDIR（临时目录）里，所以必须显式指定资源根目录。
        TCHAR resPath[MAX_PATH] = {0};
        lstrcpyn(resPath, m_folder.GetData(), MAX_PATH);
        size_t n = lstrlen(resPath);
        if (n > 0 && resPath[n - 1] != _T('\\') && resPath[n - 1] != _T('/')) {
            resPath[n] = _T('\\');
            resPath[n + 1] = 0;
        }
        CPaintManagerUI::SetResourcePath(resPath);
        m_file = file ? file : _T("");

        if (iconPath && *iconPath) {
            m_icon = (HICON)LoadImage(NULL, iconPath, IMAGE_ICON, 0, 0,
                                      LR_LOADFROMFILE | LR_DEFAULTSIZE);
        }
    }

    void InitWindow() {
        if (m_icon) {
            ::SendMessage(m_hwnd, WM_SETICON, ICON_SMALL, (LPARAM)m_icon);
            ::SendMessage(m_hwnd, WM_SETICON, ICON_BIG, (LPARAM)m_icon);
        }
        CenterWindow();
        ::ShowWindow(m_hwnd, SW_SHOWNORMAL);
        ::UpdateWindow(m_hwnd);
    }

    void Bind(const TStr& name, int fnIndex) { m_callbacks[name] = fnIndex; }

    void Notify(TNotifyUI& msg) {
        // 脚本回调正在执行时不再接受新的点击 ——
        // 否则会在 ExecuteCodeSegment 里再嵌一层 NSIS 解释器。
        if (m_inCallback) return;
        if (msg.sType != DUI_MSGTYPE_CLICK || !msg.pSender) return;

        TStr name = ToStr(msg.pSender->GetName().GetData());

        // 最小化是窗口自己的事，不用绕回脚本
        if (name == _T("btnMin")) {
            if (m_hwnd) ::ShowWindow(m_hwnd, SW_MINIMIZE);
            return;
        }

        std::map<TStr, int>::iterator it = m_callbacks.find(name);
        if (it != m_callbacks.end()) {
            m_lastCallback = it->second;
            m_inCallback = true;
            RunScript(it->second);
            m_inCallback = false;
        }
    }

    void SetCaption(LPCTSTR s) {
        if (m_hwnd && s) ::SetWindowText(m_hwnd, s);
    }

    void SetText(LPCTSTR name, LPCTSTR text) {
        CControlUI* ctl = m_PaintManager.FindControl(name);
        if (ctl) ctl->SetText(text ? text : _T(""));
    }

    void ShowPage(int index) {
        CTabLayoutUI* tab =
            dynamic_cast<CTabLayoutUI*>(m_PaintManager.FindControl(_T("wizardTab")));
        if (tab) {
            tab->SelectItem(index);
            DumpRectsToEnv();
        }
    }

    // 调试钩子：设了环境变量 VOB_SKIN_RECTS 的话，
    // 每次切页都把当前可见控件的坐标追加到那个文件里。
    // Duilib 所有控件都画在同一个 HWND 上，没法用 FindWindowEx 找控件，
    // 自动化测试要点击按钮就靠这份坐标。
    void DumpRectsToEnv() {
        TCHAR path[MAX_PATH] = {0};
        if (::GetEnvironmentVariable(_T("VOB_SKIN_RECTS"), path, MAX_PATH) <= 0) return;
        HANDLE f = ::CreateFile(path, GENERIC_WRITE,
                                FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                                OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (f == INVALID_HANDLE_VALUE) return;
        ::SetFilePointer(f, 0, NULL, FILE_END);
        // 一段一段地追加，测试脚本取最后一段就是当前这一页
        const TCHAR sep[] = _T("###\n");
        DWORD written = 0;
        ::WriteFile(f, sep, (lstrlen(sep)) * sizeof(TCHAR), &written, NULL);
        DumpControlRects(m_PaintManager.GetRoot(), f);
        ::CloseHandle(f);
    }

    // 在脚本回调里原地转一小会儿消息循环。
    // 「正在安装」这类页面光切过去是不画出来的（消息循环被脚本占着），
    // 不转一下就看不到进度条在动。
    void Delay(int ms) {
        if (ms <= 0 || !m_hwnd) return;
        DWORD start = ::GetTickCount();
        MSG msg;
        while ((int)(::GetTickCount() - start) < ms) {
            DWORD r = ::MsgWaitForMultipleObjects(0, NULL, FALSE, 20, QS_ALLINPUT);
            if (r == WAIT_OBJECT_0) {
                while (::PeekMessage(&msg, NULL, 0, 0, PM_REMOVE)) {
                    if (msg.message == WM_QUIT) {
                        m_done = true;
                        return;
                    }
                    ::TranslateMessage(&msg);
                    ::DispatchMessage(&msg);
                }
            }
            ::RedrawWindow(m_hwnd, NULL, NULL,
                           RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN);
        }
    }

    LRESULT OnClose(UINT, WPARAM, LPARAM, BOOL& bHandled) {
        // 关掉窗口等同于点标题条的叉：走同一个回调，让脚本决定是退出还是拦下
        std::map<TStr, int>::iterator it = m_callbacks.find(TStr(_T("btnClose")));
        if (it != m_callbacks.end()) {
            m_lastCallback = it->second;
            RunScript(it->second);
        } else {
            m_done = true;
        }
        bHandled = TRUE;
        return 0;
    }

    HWND GetHandle() const { return m_hwnd; }
    void SetHandle(HWND h) { m_hwnd = h; }
    CControlUI* FindControl(LPCTSTR name) { return m_PaintManager.FindControl(name); }
    CControlUI* GetRootControl() { return m_PaintManager.GetRoot(); }

    // ---- 消息循环 ----
    void RunLoop() {
        MSG msg;
        DWORD lastDump = 0;
        while (!m_done) {
            DWORD r = ::MsgWaitForMultipleObjects(0, NULL, FALSE, 50, QS_ALLINPUT);
            if (r == WAIT_OBJECT_0) {
                while (::PeekMessage(&msg, NULL, 0, 0, PM_REMOVE)) {
                    if (msg.message == WM_QUIT) {
                        // 有人让整个安装程序退出
                        m_done = true;
                        break;
                    }
                    ::TranslateMessage(&msg);
                    ::DispatchMessage(&msg);
                }
            }
            // 脚本要求继续下一步：再跑一次上一次的回调。
            // 回调之间消息循环会继续转，所以进度条能实时刷新。
            if (m_continue) {
                m_continue = false;
                if (m_lastCallback) RunScript(m_lastCallback);
            }
            // 定期把当前可见控件的坐标写出去（自动化测试找按钮用）
            DWORD now = ::GetTickCount();
            if (now - lastDump >= 400) {
                lastDump = now;
                DumpRectsToEnv();
            }
        }
    }

    void RequestContinue() { m_continue = true; }
    void RequestFinish() { m_done = true; }

public:
    HWND m_hwnd;
    HWND m_owner;
    HICON m_icon;
    extra_parameters* m_ep;
    CDuiString m_folder;
    CDuiString m_file;
    std::map<TStr, int> m_callbacks;

private:
    // 调用 NSIS 脚本函数。fnIndex 是 GetFunctionAddress 给的值（序号 + 1）。
    void RunScript(int fnIndex) {
        if (!m_ep || !m_ep->ExecuteCodeSegment) return;
        m_ep->ExecuteCodeSegment(fnIndex - 1, NULL);
    }

    bool m_done;
    bool m_continue;
    int m_lastCallback;
    bool m_inCallback;
};

// 全局单例：NSIS 一次只会跑一个安装界面
SkinWindow* g_skin = NULL;
HMODULE g_module = NULL;

// NSIS 会在每次插件调用后卸载插件（Plugins_CanUnload）。
// 注册一个 callback 就能让它把插件留在内存里 —— 否则每次调用都是一个
// 全新的模块实例，窗口句柄、回调表全丢。
UINT_PTR __cdecl SkinPluginCallback(enum NSPIM msg) {
    if (msg == NSPIM_UNLOAD && g_skin) {
        delete g_skin;
        g_skin = NULL;
    }
    return 0;
}

SkinWindow* EnsureSkin() {
    if (!g_skin) g_skin = new SkinWindow();
    return g_skin;
}

// ---------------------------------------------------------------------------
//  选择安装目录
//
//  用 IFileDialog（Vista+ 的现代文件夹选择器），比 SHBrowseForFolder 那个
//  老式壳对话框干净得多，也跟皮肤的风格更配。
// ---------------------------------------------------------------------------
bool PickFolder(HWND owner, LPCTSTR initial, LPTSTR out, int cch) {
    if (!owner) owner = NULL;
    IFileDialog* pfd = NULL;
    HRESULT hr = CoCreateInstance(CLSID_FileOpenDialog, NULL,
                                  CLSCTX_INPROC_SERVER, IID_IFileDialog,
                                  (void**)&pfd);
    if (SUCCEEDED(hr) && pfd) {
        DWORD opts = 0;
        pfd->GetOptions(&opts);
        pfd->SetOptions(opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM |
                        FOS_PATHMUSTEXIST);
        pfd->SetTitle(_T("选择安装位置"));
        if (initial && *initial) {
            IShellItem* folder = NULL;
            hr = SHCreateItemFromParsingName(initial, NULL, IID_IShellItem,
                                             (void**)&folder);
            if (SUCCEEDED(hr) && folder) {
                pfd->SetFolder(folder);
                folder->Release();
            }
        }
        hr = pfd->Show(owner);
        if (SUCCEEDED(hr)) {
            IShellItem* item = NULL;
            hr = pfd->GetResult(&item);
            if (SUCCEEDED(hr) && item) {
                PWSTR path = NULL;
                if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
                    lstrcpyn(out, path, cch);
                    CoTaskMemFree(path);
                }
                item->Release();
            }
        }
        pfd->Release();
        if (out[0]) return true;
    }
    out[0] = 0;
    return false;
}

// 把窗口区域抓下来存成 BMP（同进程抓屏，不受 DPI 虚拟化 / z 序影响），
// 用来人工核对皮肤。
void CaptureWindow(HWND wnd, LPCTSTR path) {
    if (!wnd || !path || !*path) return;

    // 置顶并强制重画，否则可能抓到被别的窗口挡住的部分
    ::SetWindowPos(wnd, HWND_TOPMOST, 0, 0, 0, 0,
                   SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER);
    ::RedrawWindow(wnd, NULL, NULL, RDW_UPDATENOW | RDW_ALLCHILDREN);
    ::UpdateWindow(wnd);
    ::Sleep(400);

    RECT rc;
    ::GetWindowRect(wnd, &rc);
    int width = rc.right - rc.left;
    int height = rc.bottom - rc.top;
    if (width <= 0 || height <= 0) return;

    HDC screen = ::GetDC(NULL);
    HDC memdc = ::CreateCompatibleDC(screen);
    HBITMAP hbm = ::CreateCompatibleBitmap(screen, width, height);
    HGDIOBJ old = ::SelectObject(memdc, hbm);
    ::BitBlt(memdc, 0, 0, width, height, screen, rc.left, rc.top, SRCCOPY);
    ::SelectObject(memdc, old);

    BITMAPINFO bi;
    ::ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = width;
    bi.bmiHeader.biHeight = height;         // 正数 = 自下而上（BMP 的要求）
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 24;
    bi.bmiHeader.biCompression = BI_RGB;
    int rowSize = ((width * 3 + 3) / 4) * 4;
    int imgSize = rowSize * height;
    BYTE* bits = (BYTE*)::HeapAlloc(GetProcessHeap(), 0, imgSize);
    if (bits) {
        if (::GetDIBits(memdc, hbm, 0, height, bits, &bi, DIB_RGB_COLORS)) {
            BITMAPFILEHEADER bfh;
            ::ZeroMemory(&bfh, sizeof(bfh));
            bfh.bfType = 0x4D42;
            bfh.bfOffBits = sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER);
            bfh.bfSize = bfh.bfOffBits + imgSize;
            HANDLE f = ::CreateFile(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                                    FILE_ATTRIBUTE_NORMAL, NULL);
            if (f != INVALID_HANDLE_VALUE) {
                DWORD written = 0;
                ::WriteFile(f, &bfh, sizeof(bfh), &written, NULL);
                ::WriteFile(f, &bi.bmiHeader, sizeof(BITMAPINFOHEADER), &written, NULL);
                ::WriteFile(f, bits, imgSize, &written, NULL);
                ::CloseHandle(f);
            }
        }
        ::HeapFree(GetProcessHeap(), 0, bits);
    }

    ::DeleteObject(hbm);
    ::DeleteDC(memdc);
    ::ReleaseDC(NULL, screen);
}

// ---------------------------------------------------------------------------
//  插件导出
// ---------------------------------------------------------------------------

// VobSkin::InitSkin <皮肤目录> <xml 文件> [图标文件]
// 只负责把窗口拉起来就返回，脚本接着可以设置标题、控件、绑定回调。
extern "C" __declspec(dllexport)
void InitSkin(HWND hwndParent, int stringt, TCHAR* vars, void* stacktop,
              extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);

    TCHAR folder[MAX_PATH] = {0};
    TCHAR file[MAX_PATH] = {0};
    TCHAR icon[MAX_PATH] = {0};
    // NSIS 把插件参数压栈时，第一个参数在栈顶，所以按书写顺序弹。
    nsis.Pop(folder, MAX_PATH);
    nsis.Pop(file, MAX_PATH);
    nsis.Pop(icon, MAX_PATH);

    // 先注册 callback，让 NSIS 别卸载我们（否则每次调用都是新实例）
    if (ep && ep->RegisterPluginCallback && g_module) {
        ep->RegisterPluginCallback(g_module, &SkinPluginCallback);
    }

    SkinWindow* skin = EnsureSkin();
    skin->Setup(hwndParent, ep, folder, file, icon);

    // NSIS 自己的对话框让位给皮肤窗口
    if (hwndParent) ::ShowWindow(hwndParent, SW_HIDE);

    if (!skin->GetHandle()) {
        HWND hwnd = skin->Create(hwndParent, _T("VOB Splitter Setup"),
                                 kSkinStyle, kSkinExStyle, 0, 0, 0, 0);
        skin->SetHandle(hwnd);
    }
}

// VobSkin::RunSkin —— 进入消息循环，直到脚本调用 Finish / Quit。
extern "C" __declspec(dllexport)
void RunSkin(HWND, int stringt, TCHAR* vars, void* stacktop,
             extra_parameters* ep) {
    SkinWindow* skin = g_skin;
    if (!skin) return;
    skin->RunLoop();

    // 关掉皮肤窗口，NSIS 的对话框重新露出来
    HWND wnd = skin->GetHandle();
    if (wnd) {
        ::ShowWindow(wnd, SW_HIDE);
        ::DestroyWindow(wnd);
    }
    if (skin->m_owner) ::ShowWindow(skin->m_owner, SW_SHOW);
}

// VobSkin::DelaySkin <毫秒>
// 在脚本回调里原地转一小会儿消息循环，让「正在安装」这类页面真的画出来。
extern "C" __declspec(dllexport)
void DelaySkin(HWND, int stringt, TCHAR* vars, void* stacktop,
               extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    int ms = 0;
    nsis.PopInt(&ms);
    if (g_skin) g_skin->Delay(ms);
}

// VobSkin::RunUninstallSkin
//   <皮肤目录> <xml 文件> <图标文件> <窗口标题> <版本> <安装路径>
//   <取消回调> <卸载回调> <完成回调>
//
// 卸载器是**另一个 exe**，NSIS 默认的插件卸载策略在那边不生效，
// 「InitSkin 一次、RunSkin 一次」的多次调用走到后面会落在一个新的模块实例上，
// 窗口直接消失。所以卸载流程整个塞进这一次调用里 —— 插件在这次调用
// 期间不会被卸载，状态自然是一致的。
extern "C" __declspec(dllexport)
void RunUninstallSkin(HWND hwndParent, int stringt, TCHAR* vars, void* stacktop,
                      extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);

    TCHAR folder[MAX_PATH] = {0};
    TCHAR file[MAX_PATH] = {0};
    TCHAR icon[MAX_PATH] = {0};
    TCHAR caption[256] = {0};
    TCHAR version[64] = {0};
    TCHAR instdir[MAX_PATH] = {0};
    int fnCancel = 0;
    int fnRun = 0;
    int fnFinish = 0;

    // NSIS 把插件参数压栈时，第一个参数在栈顶，所以按书写顺序弹。
    nsis.Pop(folder, MAX_PATH);
    nsis.Pop(file, MAX_PATH);
    nsis.Pop(icon, MAX_PATH);
    nsis.Pop(caption, 256);
    nsis.Pop(version, 64);
    nsis.Pop(instdir, MAX_PATH);
    nsis.PopInt(&fnCancel);
    nsis.PopInt(&fnRun);
    nsis.PopInt(&fnFinish);

    if (ep && ep->RegisterPluginCallback && g_module) {
        ep->RegisterPluginCallback(g_module, &SkinPluginCallback);
    }

    SkinWindow* skin = EnsureSkin();
    skin->Setup(hwndParent, ep, folder, file, icon);
    if (hwndParent) ::ShowWindow(hwndParent, SW_HIDE);

    if (!skin->GetHandle()) {
        HWND hwnd = skin->Create(hwndParent, _T("VOB Splitter Uninstaller"),
                                 kSkinStyle, kSkinExStyle, 0, 0, 0, 0);
        skin->SetHandle(hwnd);
    }

    skin->SetCaption(caption);
    skin->SetText(_T("lblVersion"), version);
    skin->SetText(_T("lblUninstallPath"), instdir);
    skin->Bind(TStr(_T("btnClose")), fnCancel);
    skin->Bind(TStr(_T("btnCancel")), fnCancel);
    skin->Bind(TStr(_T("btnUninstall")), fnRun);
    skin->Bind(TStr(_T("btnFinish")), fnFinish);

    skin->ShowPage(0);
    skin->RunLoop();

    HWND wnd = skin->GetHandle();
    if (wnd) {
        ::ShowWindow(wnd, SW_HIDE);
        ::DestroyWindow(wnd);
    }
}

extern "C" __declspec(dllexport)
void SetSkinControl(HWND, int stringt, TCHAR* vars, void* stacktop,
                    extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR value[1024] = {0};
    TCHAR attr[64] = {0};
    TCHAR name[256] = {0};
    nsis.Pop(name, 256);
    nsis.Pop(attr, 64);
    nsis.Pop(value, 1024);

    SkinWindow* skin = g_skin;
    if (!skin) return;
    CControlUI* ctl = skin->FindControl(name);
    if (!ctl) return;

    TStr a = ToStr(attr);
    if (a == _T("text")) {
        ctl->SetText(value);
        return;
    }
    if (a == _T("enabled")) {
        TStr v = ToStr(value);
        ctl->SetEnabled(v == _T("true") || v == _T("1"));
        return;
    }
    if (a == _T("visible")) {
        TStr v = ToStr(value);
        ctl->SetVisible(v == _T("true") || v == _T("1"));
        return;
    }
    if (a == _T("pos")) {
        int v[4] = { 0, 0, 0, 0 };
        if (ParseIntList(value, v, 4)) {
            RECT rc = { v[0], v[1], v[0] + v[2], v[1] + v[3] };
            ctl->SetPos(rc);
        }
        return;
    }
    // 其余的（textcolor / bkcolor / value / min / max / selected ...）
    // 交给控件自己解析，各控件的 SetAttribute 都实现了。
    ctl->SetAttribute(attr, value);
}

extern "C" __declspec(dllexport)
void GetSkinControl(HWND, int stringt, TCHAR* vars, void* stacktop,
                    extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR attr[64] = {0};
    TCHAR name[256] = {0};
    nsis.Pop(name, 256);
    nsis.Pop(attr, 64);

    SkinWindow* skin = g_skin;
    if (!skin) return;
    CControlUI* ctl = skin->FindControl(name);
    if (!ctl) {
        nsis.Push(_T(""));
        return;
    }

    TStr a = ToStr(attr);
    if (a == _T("text")) {
        nsis.Push(ctl->GetText().GetData());
    } else if (a == _T("selected")) {
        COptionUI* p = dynamic_cast<COptionUI*>(ctl);
        nsis.Push((p && p->IsSelected()) ? _T("1") : _T("0"));
    } else {
        nsis.Push(ctl->GetAttribute(attr).GetData());
    }
}

// VobSkin::BindSkinCallback <控件名> <NSIS 函数序号>
extern "C" __declspec(dllexport)
void BindSkinCallback(HWND, int stringt, TCHAR* vars, void* stacktop,
                       extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR name[256] = {0};
    nsis.Pop(name, 256);
    int fnIndex = 0;
    nsis.PopInt(&fnIndex);

    SkinWindow* skin = g_skin;
    if (!skin) return;
    skin->Bind(ToStr(name), fnIndex);
}

// VobSkin::ShowSkinPage <页序号>
extern "C" __declspec(dllexport)
void ShowSkinPage(HWND, int stringt, TCHAR* vars, void* stacktop,
                  extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    int index = 0;
    nsis.PopInt(&index);

    SkinWindow* skin = g_skin;
    if (!skin) return;
    CTabLayoutUI* tab =
        dynamic_cast<CTabLayoutUI*>(skin->FindControl(_T("wizardTab")));
    if (tab) tab->SelectItem(index);
}

extern "C" __declspec(dllexport)
void SetSkinCaption(HWND, int stringt, TCHAR* vars, void* stacktop,
                    extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR title[256] = {0};
    nsis.Pop(title, 256);

    SkinWindow* skin = g_skin;
    if (!skin || !skin->GetHandle()) return;
    ::SetWindowText(skin->GetHandle(), title);
}

// VobSkin::ContinueSkin —— 让插件再跑一次刚才那个脚本回调（做下一步）
extern "C" __declspec(dllexport)
void ContinueSkin(HWND, int stringt, TCHAR* vars, void* stacktop,
                  extra_parameters* ep) {
    SkinWindow* skin = g_skin;
    if (!skin) return;
    skin->RequestContinue();
}

// VobSkin::FinishSkin —— 流程结束，回到 NSIS 继续
extern "C" __declspec(dllexport)
void FinishSkin(HWND, int stringt, TCHAR* vars, void* stacktop,
                extra_parameters* ep) {
    SkinWindow* skin = g_skin;
    if (!skin) return;
    skin->RequestFinish();
}

// VobSkin::QuitSkin —— 用户放弃，直接退出安装程序
extern "C" __declspec(dllexport)
void QuitSkin(HWND, int stringt, TCHAR* vars, void* stacktop,
              extra_parameters* ep) {
    SkinWindow* skin = g_skin;
    if (!skin) return;
    skin->RequestFinish();
    // NSIS 的「退出」就是往线程队列里塞一个 WM_QUIT（见 NSIS 的 EW_QUIT）
    ::PostQuitMessage(0);
}

// VobSkin::BrowseFolder <起始目录> —— 弹出文件夹选择器，选中路径压回栈里
extern "C" __declspec(dllexport)
void BrowseFolder(HWND, int stringt, TCHAR* vars, void* stacktop,
                  extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR initial[MAX_PATH] = {0};
    nsis.Pop(initial, MAX_PATH);

    TCHAR result[MAX_PATH] = {0};
    HWND owner = g_skin ? g_skin->GetHandle() : NULL;
    if (PickFolder(owner, initial, result, MAX_PATH)) {
        nsis.Push(result);
    } else {
        nsis.Push(_T(""));
    }
}

// VobSkin::SavePreview <bmp 路径> —— 把当前窗口区域截下来存成 BMP（调试用）
extern "C" __declspec(dllexport)
void SavePreview(HWND, int stringt, TCHAR* vars, void* stacktop,
                 extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR path[MAX_PATH] = {0};
    nsis.Pop(path, MAX_PATH);
    CaptureWindow(g_skin ? g_skin->GetHandle() : NULL, path);
}

// 把控件树的位置写成一个文本文件（自动化测试用来找按钮坐标）。
// Duilib 所有控件都画在同一个 HWND 上，没法用 FindWindowEx 找，
// 所以只能由插件自己报坐标。
void DumpControlRects(CControlUI* ctl, HANDLE f) {
    if (!ctl || f == INVALID_HANDLE_VALUE) return;
    if (ctl->IsVisible()) {
        RECT rc = ctl->GetPos();
        TCHAR buf[512];
        _stprintf_s(buf, 512, _T("%s\t%d\t%d\t%d\t%d\n"),
                    ctl->GetName().GetData(),
                    rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top);
        DWORD written = 0;
        ::WriteFile(f, buf, lstrlen(buf) * sizeof(TCHAR), &written, NULL);
    }
    CContainerUI* cont = dynamic_cast<CContainerUI*>(ctl);
    if (!cont) return;
    for (int i = 0; i < cont->GetCount(); ++i) {
        DumpControlRects(cont->GetItemAt(i), f);
    }
}
// VobSkin::DumpSkinRects <txt 路径> —— 导出各控件的坐标（自动化测试用）
extern "C" __declspec(dllexport)
void DumpSkinRects(HWND, int stringt, TCHAR* vars, void* stacktop,
                   extra_parameters* ep) {
    NsisBridge nsis(stringt, stacktop);
    TCHAR path[MAX_PATH] = {0};
    nsis.Pop(path, MAX_PATH);
    SkinWindow* skin = g_skin;
    if (!skin || !path || !*path) return;

    HANDLE f = ::CreateFile(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                            FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return;
    DumpControlRects(skin->GetRootControl(), f);
    ::CloseHandle(f);
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = hModule;
        ::DisableThreadLibraryCalls(hModule);
        CPaintManagerUI::SetInstance(hModule);
        // 文件夹选择器要用 COM。NSIS 自己已经初始化过了，这里只是加个引用计数；
        // 万一模型不一致返回 RPC_E_CHANGED_MODE，也不影响 IFileDialog 使用。
        ::CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    }
    return TRUE;
}

}  // namespace
