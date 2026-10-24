param([ValidateSet('pdf','directory')][string]$Kind, [string]$InitialPathBase64 = 'EMPTY')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace PdfTranslator {
  [ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")] class FileOpenDialog {}
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Filter {
    [MarshalAs(UnmanagedType.LPWStr)] public string Name;
    [MarshalAs(UnmanagedType.LPWStr)] public string Pattern;
  }
  [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItem {
    void BindToHandler(); void GetParent();
    void GetDisplayName(uint kind, out IntPtr name);
    void GetAttributes(); void Compare();
  }
  [ComImport, Guid("D57C7288-D4AD-4768-BE02-9D969532D960"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFileOpenDialog {
    [PreserveSig] int Show(IntPtr owner);
    void SetFileTypes(uint count, [MarshalAs(UnmanagedType.LPArray, SizeParamIndex=0)] Filter[] filters);
    void SetFileTypeIndex(uint index); void GetFileTypeIndex(); void Advise(); void Unadvise();
    void SetOptions(uint options); void GetOptions(out uint options);
    void SetDefaultFolder(IShellItem folder); void SetFolder(IShellItem folder);
    void GetFolder(); void GetCurrentSelection(); void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetFileName(); void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string label); void SetFileNameLabel();
    void GetResult(out IShellItem item);
  }
  public static class Picker {
    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr context, ref Guid iid, out IShellItem item);
    public static string Select(bool folder, string initial, IntPtr owner) {
      var dialog=(IFileOpenDialog)new FileOpenDialog();
      try {
        uint options; dialog.GetOptions(out options);
        dialog.SetOptions(options | 0x40u | 0x800u | 0x02000000u | (folder ? 0x20u : 0x1000u));
        dialog.SetTitle(folder ? "选择 PDF 翻译输出目录" : "选择要翻译的 PDF");
        if(!folder)dialog.SetFileTypes(1,new[]{new Filter{Name="PDF 文档 (*.pdf)",Pattern="*.pdf"}});
        if(!String.IsNullOrWhiteSpace(initial) && System.IO.Directory.Exists(initial)) {
          IShellItem location; var iid=typeof(IShellItem).GUID;
          SHCreateItemFromParsingName(System.IO.Path.GetFullPath(initial),IntPtr.Zero,ref iid,out location);
          try {dialog.SetFolder(location);} finally {Marshal.ReleaseComObject(location);}
        }
        int result=dialog.Show(owner);
        if(result==unchecked((int)0x800704C7))return null;
        Marshal.ThrowExceptionForHR(result);
        IShellItem selected; dialog.GetResult(out selected);
        try {
          IntPtr value; selected.GetDisplayName(0x80058000,out value);
          try {return Marshal.PtrToStringUni(value);} finally {Marshal.FreeCoTaskMem(value);}
        } finally {Marshal.ReleaseComObject(selected);}
      } finally {Marshal.ReleaseComObject(dialog);}
    }
  }
}
'@
$initial = if ($InitialPathBase64 -eq 'EMPTY') { '' } else { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($InitialPathBase64)) }
# The native dialog owns its window; a hidden helper form can hide owned dialogs.
$selected = [PdfTranslator.Picker]::Select(($Kind -eq 'directory'), $initial, [IntPtr]::Zero)
if ($null -eq $selected) { @{cancelled=$true} | ConvertTo-Json -Compress }
else { @{cancelled=$false;path=$selected} | ConvertTo-Json -Compress }
