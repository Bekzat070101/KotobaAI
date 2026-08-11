<?xml version="1.0" encoding="utf-8"?>
<!--
  KOTOBA·AI MSIX 清单模板（占位符由 render_manifest.ps1 填充）
  上架前必须把 __NAME__ / __PUBLISHER__ 换成 Partner Center 预留值（差一个字符都会被拒）。
-->
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">

  <Identity Name="__NAME__"
            Publisher="__PUBLISHER__"
            Version="__VERSION__"
            ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>KOTOBA·AI</DisplayName>
    <PublisherDisplayName>__PUBLISHER_DISPLAY__</PublisherDisplayName>
    <Description>日语语法 AI 闯关练习工具 · 本地优先 · 免费开源</Description>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop"
                        MinVersion="__MIN_VERSION__"
                        MaxVersionTested="__MAX_VERSION__" />
  </Dependencies>

  <Resources>
    <Resource Language="zh-CN" />
    <Resource Language="en-US" />
  </Resources>

  <Applications>
    <Application Id="App"
                 Executable="KOTOBA-AI.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="KOTOBA·AI"
                          Description="日语语法 AI 闯关练习工具"
                          Square150x150Logo="Assets\Logo150x150.png"
                          Square44x44Logo="Assets\Logo44x44.png"
                          BackgroundColor="#F00000" />
    </Application>
  </Applications>

  <Capabilities>
    <!-- 桌面应用必须：以完整权限运行（非 UWP 沙箱应用） -->
    <rescap:Capability Name="runFullTrust" />
    <!-- 联网：访问 DeepSeek API -->
    <Capability Name="internetClient" />
  </Capabilities>
</Package>
