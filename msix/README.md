# msix/ — 微软商店版打包线（M8）

把根目录 `build.bat` 打出的 onedir 再包一层 MSIX，供微软商店上架。

## 文件

| 文件 | 作用 |
|------|------|
| `build_msix.bat` | 主打包脚本：清 staging → 生成图标 → 渲染清单 → 复制 onedir → MakeAppx → 自签名 |
| `AppxManifest.xml.tpl` | 清单模板，`__NAME__` 等占位符由脚本填充 |
| `make_assets.py` | 从 `static/logo_icon.png` 生成 StoreLogo/150/44 三个 PNG 图标 |
| `render_manifest.ps1` | 用配置值替换模板占位符，输出 UTF-8 无 BOM 清单 |
| `make_dev_cert.ps1` | 生成本地测试用自签名代码签名证书（仅真机验证用） |

## 使用

前置：先在项目根目录跑一次 `build.bat`，确保 `dist\KOTOBA-AI\`（exe + _internal）存在。

```bash
cmd //c "C:\Users\Aa233\Desktop\JapAI\msix\build_msix.bat"
```

产出：`msix/KOTOBA-AI-4.0.1.0-x64.msix` + `dev_cert.pfx/.cer`。脚本末尾可交互选择「装入本机做真机验证」。

> **真机验证装包必读**：`Add-AppxPackage` 的部署服务（AppXSvc）以 SYSTEM 身份运行，只认**本机（LocalMachine）**证书存储——导入用户级（CurrentUser）存储会一直报 `0x800B0109`（签名的根不受信任）。所以必须**以管理员身份**的 PowerShell 执行：
> ```powershell
> # 管理员 PowerShell
> Import-Certificate -FilePath 'C:\Users\Aa233\Desktop\JapAI\msix\dev_cert.cer' -CertStoreLocation Cert:\LocalMachine\Root
> Import-Certificate -FilePath 'C:\Users\Aa233\Desktop\JapAI\msix\dev_cert.cer' -CertStoreLocation Cert:\LocalMachine\TrustedPeople
> # 普通 PowerShell
> Add-AppxPackage -Path 'C:\Users\Aa233\Desktop\JapAI\msix\KOTOBA-AI-4.0.1.0-x64.msix'
> ```
> 若此前从未侧载过 MSIX，还需开启「开发人员模式」（设置 → 系统 → 开发者选项）。`build_msix.bat` 的交互安装段已按此逻辑实现，管理员权限跑整包即可。

## 上架前必改

`build_msix.bat` 顶部的两个值：

- `MSIX_NAME` ← 换成 Partner Center 后台预留的应用名（如 `34929BekzatXxx.KotobaAI`）
- `MSIX_PUBLISHER` ← 换成后台显示的发布者（`CN=……`）

> `Identity.Name / Publisher` 与 Partner Center 预留值必须**完全一致**，差一个字符都会被拒。
> 本地测试可保持默认值不动；上架包由微软重签，无需本地证书。

## 商店版与 GitHub 版

- **数据互通**（M8.2 实测确认）：full-trust（runFullTrust）MSIX **不做 `%APPDATA%` 重定向**——商店版与 GitHub 版读写**同一个** `%APPDATA%\KOTOBA-AI` 数据目录。实测商店版启动后 `is_packaged()=true`，但 `dir` 指向真实 APPDATA、沙箱 `LocalCache\Roaming` 下无 KOTOBA-AI 目录。这对用户是好事：数据统一，切版本不丢进度。
- 商店版设置页**不提供**「自定义数据目录」入口（见 PRD DIR-1，M8.2 代码适配：`paths.is_packaged()` 为真时 `get_data_dir()` 锁定默认目录、`set_data_dir()` 直接抛错，前端隐藏更改按钮并提示）。
- 商店版安装由微软重签，**无 SmartScreen 警告**；GitHub 版保持现状。

## 商店提交流程（M8.4）

1. 注册 Partner Center 免费个人账户（微软账号 + 实名验证）
2. 新建产品 → 预留应用名 → 记下 Name / Publisher 填回脚本
3. 本机 WACK 自测通过（脚本末尾给了命令行 / GUI 入口）
4. 提交 .msix + 元数据（描述、截图 ≥1366×768、隐私政策 URL、分类/年龄/定价免费）
5. 微软审核（数天到两周）→ 上架后商店内一键安装、自动更新

## 体积备注

onedir 约 410MB（OCR 模型 9.4MB + 知识库 508 语法点 + Python 运行时），商店包同量级。MSIX 是否压缩/外置模型见 PRD MSIX-5，P2 不阻塞上架。
